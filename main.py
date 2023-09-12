import sys

import grpc
import demo_pb2
import demo_pb2_grpc
from concurrent import futures

# define the gRPC service class
class CheckoutService(demo_pb2_grpc.CheckoutServiceServicer):
    def PlaceOrder(self, request, context):
        order_result = demo_pb2.OrderResult(
            order_id='123',
            status='success'
        )
        response = demo_pb2.PlaceOrderResponse(
            order=order_result
        )
        return response

class ServerControlService(demo_pb2_grpc.ServerControlService):
    def TerminateServer(self, request, context):
        if request.action == 'terminate':
            print("terminating server")
            server.stop(0)
        return demo_pb2.Empty()

# create a gRPC server and add the service to it
server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
demo_pb2_grpc.add_CheckoutServiceServicer_to_server(CheckoutService(), server)
demo_pb2_grpc.add_ServerControlServiceServicer_to_server(ServerControlService(), server)
server.add_insecure_port('[::]:50051')

# start the server
server.start()
print('Server started on port 50051')

# wait for the server to finish
server.wait_for_termination()