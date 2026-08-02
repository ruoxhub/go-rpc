package cn.iinti.sekiro3.business.api.core;

import cn.iinti.sekiro3.business.api.SekiroClient;
import cn.iinti.sekiro3.business.api.core.compress.NettyCompressHandler;
import cn.iinti.sekiro3.business.api.core.compress.NettyDecompressHandler;
import cn.iinti.sekiro3.business.api.interfaze.SekiroRequest;
import cn.iinti.sekiro3.business.api.interfaze.SekiroResponse;
import cn.iinti.sekiro3.business.api.log.SekiroLogger;
import cn.iinti.sekiro3.business.api.protocol.SekiroPackerEncoder;
import cn.iinti.sekiro3.business.api.protocol.SekiroPacket;
import cn.iinti.sekiro3.business.api.protocol.SekiroPacketDecoder;
import cn.iinti.sekiro3.business.api.protocol.SekiroPacketType;
import cn.iinti.sekiro3.business.api.util.Constants;
import io.netty.bootstrap.Bootstrap;
import io.netty.channel.*;
import io.netty.channel.nio.NioEventLoopGroup;
import io.netty.channel.socket.SocketChannel;
import io.netty.channel.socket.nio.NioSocketChannel;
import io.netty.handler.timeout.IdleState;
import io.netty.handler.timeout.IdleStateEvent;
import io.netty.handler.timeout.IdleStateHandler;
import lombok.Getter;

import java.util.concurrent.TimeUnit;

public class SekiroClientConnection extends SimpleChannelInboundHandler<SekiroPacket> {
    /**
     * 线程池需要全局共享，否则多client同时工作会内存溢出，此线程池不需要特殊设定，
     */
    private static final EventLoopGroup eventLoopGroup = new NioEventLoopGroup();

    @Getter
    private final SekiroClient sekiroClient;
    @Getter
    private Channel channel;


    private final SekiroLogger sekiroLogger;

    public SekiroClientConnection(final SekiroClient sekiroClient, String serverHost, int port) {
        this.sekiroClient = sekiroClient;
        this.sekiroLogger = sekiroClient.getSekiroLogger();

        // 说明下，对于单tcp通道来说，没必要上netty，
        // sekiro的client使用netty受限于历史原因（最早版本实现是对网络不太懂导致的），另外也算是一个netty使用案例教学，
        // 但是用它作为客户端有点过于重了，这是因为work connection只有一个，不会出现io多路复用的场景
        Bootstrap bootstrap = new Bootstrap();
        bootstrap.group(eventLoopGroup).channel(NioSocketChannel.class)
                .handler(new ChannelInitializer<SocketChannel>() {
                    @Override
                    protected void initChannel(SocketChannel ch) {
                        // 客户端在连接的时候就可以确定logger了
                        ch.pipeline()
                                .addLast(new SekiroPackerEncoder(),
                                        new NettyCompressHandler(sekiroClient.getCompressorManager(), false),
                                        new SekiroPacketDecoder(),
                                        new NettyDecompressHandler(sekiroClient.getCompressorManager(), false),
                                        new IdleStateHandler(Constants.SERVER_READ_IDLE + 35, 0, 0),
                                        SekiroClientConnection.this);
                    }
                });

        eventLoopGroup.next().execute(() -> {
            sekiroLogger.info("begin to connect to upstream-> " + serverHost + ":" + port);
            // for android, connect method invoke can not in main thread
            ChannelFuture channelFuture = bootstrap.connect(serverHost, port);
            channel = channelFuture.channel();
            channelFuture.addListener(new ConnectionListener());
        });
    }

    @Override
    protected void channelRead0(ChannelHandlerContext ctx, SekiroPacket msg) {
        SekiroPacketType packetType = SekiroPacketType.getByCode(msg.getType());
        if (packetType == null) {
            sekiroLogger.error("unknown sekiro message type");
            return;
        }
        sekiroLogger.info("receive message from sekiro server:" + packetType);

        switch (packetType) {
            case S_TYPE_INVOKE:
                int seq = msg.getSerialNumber();
                if (seq < 0) {
                    sekiroLogger.error("the serial number not set");
                    ctx.close();
                    return;
                }
                SekiroRequest sekiroRequest = new SekiroRequest(sekiroClient, msg);
                SekiroResponse sekiroResponse = new SekiroResponse(ctx.channel(), sekiroRequest);
                HandlerThreadPool.post(new RequestTaskRunner(sekiroRequest, sekiroResponse));
                break;
            case TYPE_HEARTBEAT:
                ctx.channel().writeAndFlush(SekiroPacketType.TYPE_HEARTBEAT.createPacket());
                break;
            case S_TYPE_OFFLINE_RESPONSE:
                //todo offline event
                break;
        }
    }

    @Override
    public void userEventTriggered(ChannelHandlerContext ctx, Object evt) throws Exception {
        if (evt instanceof IdleStateEvent) {
            IdleStateEvent event = (IdleStateEvent) evt;
            if (event.state() == IdleState.READER_IDLE) {
                sekiroLogger.error("sekiro read idle timeout, close channel");
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

    private class ConnectionListener implements ChannelFutureListener {
        private EventLoop workThread(Channel channel) {
            if (channel == null) {
                return eventLoopGroup.next();
            }
            return channel.eventLoop();
        }

        @Override
        public void operationComplete(ChannelFuture future) {
            //特殊场景下，channel可能为null，不过这不重要
            final EventLoop eventLoop = workThread(future.channel());
            if (!future.isSuccess()) {
                sekiroLogger.error("connect to sekiro server failed", future.cause());
                sekiroClient.onClientOpDestroy(eventLoop, SekiroClientConnection.this);
                return;
            }


            channel.closeFuture().addListener((ChannelFutureListener) future1 -> sekiroClient.onClientOpDestroy(eventLoop, SekiroClientConnection.this));

            if (sekiroClient.isDestroyed()) {
                sekiroLogger.info("connect success after sekiroClient destroyed, close connection");
                channel.close();
                return;
            }

            SekiroPacket packet = SekiroPacketType.C_TYPE_REGISTER.createPacket();
            packet.addHeader(Constants.COMMON_HEADERS.HEADER_CLIENT_ID, sekiroClient.getClientId());
            packet.addHeader(Constants.COMMON_HEADERS.HEADER_SEKIRO_GROUP, sekiroClient.getSekiroGroup());
            channel.writeAndFlush(packet)
                    .addListener((ChannelFutureListener) future12 -> {
                        if (future12.isSuccess()) {
                            sekiroClient.onClientOpOnline();
                            return;
                        }
                        sekiroLogger.error("write sekiro register cmd failed", future12.cause());
                        future12.channel().close();
                    });
        }
    }

    public void destroy(long waitSeconds) {
        if (channel == null) {
            sekiroClient.triggerClientDestroy();
            return;
        }
        //  给服务器发送设备离线指令，之后服务器将会摘除流量
        channel.writeAndFlush(SekiroPacketType.C_TYPE_OFFLINE.createPacket());
        channel.eventLoop().schedule(() -> {
            sekiroClient.triggerClientDestroy();

            // close
            channel.eventLoop().schedule(() -> {
                channel.close();
            }, 60, TimeUnit.SECONDS);
        }, waitSeconds, TimeUnit.SECONDS);
    }
}
