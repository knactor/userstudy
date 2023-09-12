import grpc
import demo_pb2_grpc
import demo_pb2

if __name__ == "__main__":
    channel = grpc.insecure_channel('localhost:50051')
    stub = demo_pb2_grpc.ServerControlServiceStub(channel)
    req = demo_pb2.ControlRequest(action="terminate")
    stub.TerminateServer(req)