#ifndef Rpc_h
#define Rpc_h

#import <Foundation/Foundation.h>

@interface RpcResponse: NSObject
- (void)success:(NSData *)d;
- (void)failed:(NSString *)m;
@end

typedef void (*RpcHandler) (NSDictionary *, RpcResponse *);

@interface RpcClient: NSObject
/*初始化，带全部参数*/
- (RpcClient *)init:(NSString *)group
                  host:(NSString *)h
                  port:(int)p
              clientId:(NSString *)c;
/*初始化，连接sekiro默认测试服务器*/
- (RpcClient *)init: (NSString *)groupVal;
/* 启动sekiro  */
- (void)start;
/* 注册处理器 */
- (void)registerAction:(NSString *)act handler:(RpcHandler)handle;
@end

#endif /* Rpc_h */
