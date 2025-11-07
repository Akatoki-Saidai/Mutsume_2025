
import threading

def hello():
    print("hello, ")

def world():
    print("world")

hello_thread = threading.Thread(target=hello)
world_thread = threading.Thread(target=world)