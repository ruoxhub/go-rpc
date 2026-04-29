# Mac-os 和 IOS

```
#import <Foundation/Foundation.h>
#include "Rpc.h"

void test(NSDictionary *request, RpcResponse *response) {
    [response success:[@"\"ok replay objective-c\""  dataUsingEncoding:NSUTF8StringEncoding]];
}


int main(int argc, const char * argv[]) {
    @autoreleasepool {
        RpcClient *client = [[RpcClient alloc] init:@"test-objective-c"];
        [client registerAction:@"testAction" handler: test];
        [client start];
        
        // sekiro启动后，运行在新的线程中，所以这里需要sleep一下，否则直接程序就结束了
        [NSThread sleepForTimeInterval:300];
    }
    return 0;
}
``` 
