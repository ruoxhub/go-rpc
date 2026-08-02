package cn.iinti.sekiro3.business.api.core;

import cn.iinti.sekiro3.business.api.core.compress.NettyCompressHandler;
import cn.iinti.sekiro3.business.api.core.compress.NettyDecompressHandler;
import cn.iinti.sekiro3.business.api.invoker.Call;
import cn.iinti.sekiro3.business.api.invoker.InvokerInstance;
import cn.iinti.sekiro3.business.api.invoker.InvokerResponse;
import cn.iinti.sekiro3.business.api.log.SekiroLogger;
import cn.iinti.sekiro3.business.api.protocol.*;
import cn.iinti.sekiro3.business.api.util.Constants;
import io.netty.bootstrap.Bootstrap;
import io.netty.channel.*;
import io.netty.channel.nio.NioEventLoopGroup;
import io.netty.channel.socket.SocketChannel;
import io.netty.channel.socket.nio.NioSocketChannel;
import io.netty.handler.timeout.IdleState;
import io.netty.handler.timeout.IdleStateEvent;
import io.netty.handler.timeout.IdleStateHandler;
import io.netty.util.concurrent.Future;
import io.netty.util.concurrent.GenericFutureListener;
import lombok.SneakyThrows;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class InvokerConnection extends SimpleChannelInboundHandler<SekiroPacket> {
    private static final EventLoopGroup eventLoopGroup = new NioEventLoopGroup();
    private final InvokerInstance invokerInstance;
    private final AtomicInteger sequenceGenerator = new AtomicInteger(1);
    private final Channel channel;
    private final ConcurrentMap<Integer, Call> callConcurrentMap = new ConcurrentHashMap<>();

    private final SekiroLogger sekiroLogger;

    @SneakyThrows
    public InvokerConnection(InvokerInstance invokerInstance, String serverHost, int port, boolean sync) {
        this.invokerInstance = invokerInstance;
        this.sekiroLogger = invokerInstance.getSekiroLogger();
        Bootstrap bootstrap = new Bootstrap();
        bootstrap.group(eventLoopGroup).channel(NioSocketChannel.class)
                .remoteAddress(new InetSocketAddress(serverHost, port))
                .handler(new ChannelInitializer<SocketChannel>() {
                    @Override
                    protected void initChannel(SocketChannel ch) {
                        ch.pipeline()
                                .addLast(new SekiroPackerEncoder(),
                                        new NettyCompressHandler(invokerInstance.getCompressorManager(), false),
                                        new SekiroPacketDecoder(),
                                        new NettyDecompressHandler(invokerInstance.getCompressorManager(), false),
                                        new IdleStateHandler(Constants.SERVER_READ_IDLE + 35, 0, 0),
                                        InvokerConnection.this);
                    }
                });

        sekiroLogger.info("begin to connect to sekiro server-> " + serverHost + ":" + port);
        ChannelFuture channelFuture = bootstrap.connect(serverHost, port);
        channel = channelFuture.channel();
        channelFuture.addListener(new ConnectionListener());

        if (sync) {
            channelFuture.sync();
            if (!channelFuture.isSuccess()) {
                throw new IllegalStateException("can connect sekiro  server: " + serverHost + ":" + port, channelFuture.cause());
            }
        }
    }

    @Override
    public void userEventTriggered(ChannelHandlerContext ctx, Object evt) throws Exception {
        if (evt instanceof IdleStateEvent) {
            IdleStateEvent event = (IdleStateEvent) evt;
            if (event.state() == IdleState.READER_IDLE) {
                sekiroLogger.error("invoker read idle timeout, close channel");
                ctx.channel().close();
                return;
            }
        }
        super.userEventTriggered(ctx, evt);
    }

    @Override
    public void exceptionCaught(ChannelHandlerContext ctx, Throwable cause) {
        sekiroLogger.error("netty handler exception", cause);
    }

    @Override
    protected void channelRead0(ChannelHandlerContext ctx, SekiroPacket sekiroPacket) {
        SekiroPacketType packetType = SekiroPacketType.getByCode(sekiroPacket.getType());
        if (packetType == null) {
            return;
        }
        switch (packetType) {
            case S_TYPE_INVOKE_RESPONSE:
            case C_TYPE_INVOKE_RESPONSE:
                handlerResponse(sekiroPacket);
                break;
            case S_TYPE_INVOKE_CONNECTED:
                // TODO
                break;
            default:
                sekiroLogger.error("unexpected packageType: " + sekiroPacket);
        }
    }

    private void handlerResponse(SekiroPacket sekiroPacket) {
        int seqId = sekiroPacket.getSerialNumber();
        InvokerResponse invokerResponse = new InvokerResponse();
        invokerResponse.setSuccessful();
        invokerResponse.setHeaders(sekiroPacket.getHeaders());
        invokerResponse.setBytes(sekiroPacket.getData());

        Call call = callConcurrentMap.remove(seqId);
        if (call == null) {
            // the call has been timeout
            return;
        }
        call.callback().onResponse(call, invokerResponse);

    }

    public void destroy(GenericFutureListener<? extends Future<? super Void>> listener) {
        channel.close().addListener(listener);
    }

    private class ConnectionListener implements ChannelFutureListener {
        @Override
        public void operationComplete(ChannelFuture future) {
            final EventLoop eventLoop = future.channel().eventLoop();
            if (!future.isSuccess()) {
                sekiroLogger.error("connect to sekiro server failed", future.cause());
                invokerInstance.onClientOpDestroy(eventLoop);
                return;
            }

            channel.closeFuture().addListener(new ChannelFutureListener() {
                @Override
                public void operationComplete(ChannelFuture future) {
                    try {
                        invokerInstance.onClientOpDestroy(eventLoop);
                    } finally {
                        onLoseServerConnection();
                    }
                }
            });

            if (invokerInstance.isDestroyed()) {
                sekiroLogger.info("connect success after invoker destroyed, close connection");
                channel.close();
                return;
            }

            SekiroPacket packet = SekiroPacketType.I_TYPE_CONNECT.createPacket();
            channel.writeAndFlush(packet).addListener(new ChannelFutureListener() {
                @Override
                public void operationComplete(ChannelFuture future) {
                    if (future.isSuccess()) {
                        invokerInstance.onClientOpOnline();
                        return;
                    }
                    sekiroLogger.error("write sekiro connect cmd failed", future.cause());
                    future.channel().close();
                }
            });

        }
    }

    public boolean isAlive() {
        return channel != null && channel.isActive();
    }

    private void handleInvokeTimeoutEvent(int seq) {
        Call remove = callConcurrentMap.remove(seq);
        if (remove == null) {
            // request has been responded
            return;
        }

        remove.callback().onFailure(remove, new IOException("sekiro->sekiro server invoke timeout"));
    }


    public void performInvoke(final Call call, final String apiToken) {
        SekiroPacket sekiroPacket = SekiroPacketType.I_TYPE_INVOKE.createPacket();
        final int seq = sequenceGenerator.incrementAndGet();
        sekiroPacket.setSerialNumber(seq);
        sekiroPacket.setHeaders(call.invokerRequest().getHeaders());
        sekiroPacket.setData(call.invokerRequest().data(apiToken));
        call.setSeq(seq);

        channel.writeAndFlush(sekiroPacket)
                .addListener(new ChannelFutureListener() {
                    @Override
                    public void operationComplete(ChannelFuture future) {
                        if (!future.isSuccess()) {
                            call.callback().onFailure(call, new IOException("failed to write invoke request ", future.cause()));
                            return;
                        }

                        callConcurrentMap.put(seq, call);

                        // fire timeout event
                        channel.eventLoop().schedule(new Runnable() {
                            @Override
                            public void run() {
                                InvokerConnection.this.handleInvokeTimeoutEvent(seq);
                            }
                        }, call.invokerRequest().timeout() + 1000, TimeUnit.MILLISECONDS);
                    }
                });
    }

    private void onLoseServerConnection() {
        for (Integer integer : callConcurrentMap.keySet()) {
            Call call = callConcurrentMap.remove(integer);
            if (call == null) {
                continue;
            }
            call.callback().onFailure(call, new IOException("sekiro server lose connection"));
        }
    }
}
