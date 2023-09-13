import inspect
import os
import random
import subprocess
import sys
import time
from concurrent import futures

import grpc
from IPython.core.magics.code import extract_symbols

import demo_pb2
import demo_pb2_grpc


def new_getfile(object, _old_getfile=inspect.getfile):
    if not inspect.isclass(object):
        return _old_getfile(object)
    
    # Lookup by parent module (as in current inspect)
    if hasattr(object, '__module__'):
        object_ = sys.modules.get(object.__module__)
        if hasattr(object_, '__file__'):
            return object_.__file__
    
    # If parent module is __main__, lookup by methods (NEW)
    for name, member in inspect.getmembers(object):
        if inspect.isfunction(member) and object.__qualname__ + '.' + member.__name__ == member.__qualname__:
            return inspect.getfile(member)
    else:
        raise TypeError('Source for {!r} not found'.format(object))
inspect.getfile = new_getfile

def stringify_class(obj):
    cell_code = "".join(inspect.linecache.getlines(new_getfile(obj)))
    class_code = extract_symbols(cell_code, obj.__name__)[0][0]
    return class_code

def generate_grpc_server(server_obj, port = 50051):
    return f"""
import sys

import grpc
import demo_pb2
import demo_pb2_grpc
from concurrent import futures

# define the gRPC service class
{stringify_class(server_obj)}
class ServerControlService(demo_pb2_grpc.ServerControlService):
    def TerminateServer(self, request, context):
        if request.action == 'terminate':
            print("terminating server")
            server.stop(0)
        return demo_pb2.Empty()

# create a gRPC server and add the service to it
server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
demo_pb2_grpc.add_{server_obj.__name__}Servicer_to_server({server_obj.__name__}(), server)
demo_pb2_grpc.add_ServerControlServiceServicer_to_server(ServerControlService(), server)
server.add_insecure_port('[::]:{port}')

# start the server
server.start()
print('Server started on port {port}')

# wait for the server to finish
server.wait_for_termination()
"""


def generate_stub(service_to_port):
    stub_registrations = []
    for service, port in service_to_port.items(): 
        stub_registrations.append(f"\t{service}_channel = grpc.insecure_channel(f'localhost:{port}')")
        stub_registrations.append(f"\t{service}_stub = demo_pb2_grpc.{service}Stub({service}_channel)")
        stub_registrations.append(f"\t{service}_stub = demo_pb2_grpc.ServerControlServiceStub({service}_channel)")
    stub_registration_code = "\n".join(stub_registrations)

    server_terminations = []
    server_terminations.append(f"\treq = demo_pb2.ControlRequest(action='terminate')")
    for service, port in service_to_port.items(): 
        server_terminations.append(f"\t{service}_stub.TerminateServer(req, timeout=1)")
    server_termination_code = "\n".join(server_terminations)

    return f"""
import grpc
import demo_pb2_grpc
import demo_pb2

if __name__ == "__main__":
{stub_registration_code}
{server_termination_code}
"""    

def test_grpc(services):
    server_processes = []
    filenames = []
    server_to_port = {}
    for obj in services:
        filename = f"{obj.__name__}.py"
        filenames.append(filename)
        port = random.randint(50000, 59999)
        server_to_port[obj.__name__] = port
        with open(filename, 'w') as f:
            f.write(generate_grpc_server(obj, port))

        process = subprocess.Popen(["python", filename], stdout=subprocess.PIPE, stderr= subprocess.PIPE)
        server_processes.append(process)
    
    with open("grpc_client.py", 'w') as f:
        f.write(generate_stub(server_to_port))
 
    time.sleep(1) # buffer for starting up servers
    stub_process = subprocess.Popen(["python", "grpc_client.py"], stdout=subprocess.PIPE, stderr= subprocess.PIPE)
    stdout, stderr = stub_process.communicate()
    
    for process in server_processes:
        stdout, stderr = process.communicate()
        print(stdout, stderr)
        
    for file in filenames:
        os.remove(file)
    os.remove('grpc_client.py')
