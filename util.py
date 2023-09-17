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
    if hasattr(object, "__module__"):
        object_ = sys.modules.get(object.__module__)
        if hasattr(object_, "__file__"):
            return object_.__file__

    # If parent module is __main__, lookup by methods (NEW)
    for name, member in inspect.getmembers(object):
        if (
            inspect.isfunction(member)
            and object.__qualname__ + "." + member.__name__ == member.__qualname__
        ):
            return inspect.getfile(member)
    else:
        raise TypeError("Source for {!r} not found".format(object))


inspect.getfile = new_getfile


def stringify_class(obj):
    cell_code = "".join(inspect.linecache.getlines(new_getfile(obj)))
    class_code = extract_symbols(cell_code, obj.__name__)[0][0]
    return class_code


def generate_grpc_server(server_obj, port=50051):
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


def generate_stub(service_to_port, test_fn=None):
    stub_registrations = []
    for service, port in service_to_port.items():
        stub_registrations.append(
            f"    {service}_channel = grpc.insecure_channel(f'localhost:{port}')"
        )
        stub_registrations.append(
            f"    {service}_stub = demo_pb2_grpc.{service}Stub({service}_channel)"
        )
        stub_registrations.append(
            f"    {service}_control_stub = demo_pb2_grpc.ServerControlServiceStub({service}_channel)"
        )
    stub_registration_code = "\n".join(stub_registrations)

    server_terminations = []
    server_terminations.append(f"    req = ControlRequest(action='terminate')")
    for service, port in service_to_port.items():
        server_terminations.append(f"    {service}_control_stub.TerminateServer(req, timeout=1)")
    server_termination_code = "\n".join(server_terminations)

    return f"""
import grpc
import demo_pb2_grpc
from demo_pb2 import *

if __name__ == "__main__":
{stub_registration_code}
{test_fn}
{server_termination_code}
"""


def create_test(test_fn):
    def test_grpc(services_port):
        server_processes = []
        filenames = []
        server_to_port = {}
        for obj, port in services_port.items():
            filename = f"{obj.__name__}.py"
            filenames.append(filename)
            server_to_port[obj.__name__] = port
            with open(filename, "w") as f:
                f.write(generate_grpc_server(obj, port))

            process = subprocess.Popen(
                ["python", filename], stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            server_processes.append(process)

        with open("grpc_client.py", "w") as f:
            f.write(generate_stub(server_to_port, test_fn))

        time.sleep(1)  # buffer for starting up servers
        stub_process = subprocess.Popen(
            ["python", "grpc_client.py"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout, stderr = stub_process.communicate()
        print(stdout, stderr)

        for process in server_processes:
            stdout, stderr = process.communicate()
            print(stdout, stderr)

        for file in filenames:
            os.remove(file)
        os.remove("grpc_client.py")

    return test_grpc


basic_test_stub_code = """
    request = PlaceOrderRequest(
        user_id="123",
        user_currency="USD",
        address=Address(
            street_address="123 Main Street",
            city="Berkeley",
            state="CA",
            country="USA",
            zip_code=94704
        ),
        email="user@example.com",
        credit_card=CreditCardInfo(
            credit_card_number="1111-2222-3333-4444",
            credit_card_cvv=123,
            credit_card_expiration_year=2023,
            credit_card_expiration_month=9
        ),
    )

    
    try:
        # Call the PlaceOrder method
        response = CheckoutService_stub.PlaceOrder(request, timeout=1)

        # Print the response
        print("Order ID:", response.order.order_id)
        print("Shipping Tracking ID:", response.order.shipping_tracking_id)
        print("Shipping Cost (USD):", response.order.shipping_cost)
        print("Shipping Address:", response.order.shipping_address)
        print("Ordered Items:")
        for item in response.order.items:
            print(f"Product ID: {item.item.product_id}, Quantity: {item.item.quantity}, Cost (USD): {item.cost}")
    
    except Exception as e:
        print(e)
"""

test_basic = create_test(basic_test_stub_code)
