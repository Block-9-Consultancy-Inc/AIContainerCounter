from multiprocessing import Process, Queue, shared_memory
import cv2
import numpy as np
from time import perf_counter
import os

def shared_memory_process(queue: Queue):
    while True:
        name, image_name, before_time, is_last = queue.get()
        shm = shared_memory.SharedMemory(name=name, track=False)
        b = np.ndarray((1080, 1920, 3), np.uint8, buffer=shm.buf)
        print(f'reading took {(perf_counter() - before_time) * 1000} ms')
        cv2.imwrite(image_name, b)
        shm.close()
        if is_last:
            return

def shared_memory_approach():
    queue = Queue()

    # Create, start, and finish the child process
    p = Process(target=shared_memory_process, args=(queue,))
    p.start()
    
    images = os.listdir('images/22e8c32f-1ed1-45a2-8c27-16ca56144dc6/multi_container_images')[:3]

    shared_memories = []
    num_images = len(images)
    for index, image in enumerate(images):
        unshared_arr = cv2.imread(f'images/22e8c32f-1ed1-45a2-8c27-16ca56144dc6/multi_container_images/{image}')
        before_time = perf_counter()
        shm = shared_memory.SharedMemory(create=True, size=unshared_arr.nbytes)
        after_allocating_time = perf_counter()
        print(f'allocating shared memory took {(after_allocating_time - before_time) * 1000} ms')
        shared_arr = np.ndarray(unshared_arr.shape, np.uint8, buffer=shm.buf)
        after_create_shared_arr_time = perf_counter()
        print(f'creating shared arr took {(after_create_shared_arr_time - after_allocating_time) * 1000} ms')
        np.copyto(shared_arr, unshared_arr)
        after_copy_array_time = perf_counter()
        print(f'copying array into shared arr took {(after_copy_array_time - after_create_shared_arr_time) * 1000} ms')
        
        queue.put((shm.name, image, before_time, index == num_images - 1))
        after_time = perf_counter()
        print(f'enqueing took {(after_time - after_copy_array_time) * 1000} ms')
        shared_memories.append(shm)
    p.join()
    for shm in shared_memories:
        shm.close()
        shm.unlink()



def copy_process(queue: Queue):
    image, before_time = queue.get()
    print(f'reading took {(perf_counter() - before_time) * 1000} ms')
    cv2.imwrite('test.jpg', image)

def copy_approach():
    queue = Queue()

    # Create, start, and finish the child process
    p = Process(target=copy_process, args=(queue,))
    p.start()

    image = cv2.imread('images/22e8c32f-1ed1-45a2-8c27-16ca56144dc6/multi_container_images/1b69d9f3-0303-41a7-baa7-cce3257afcd0.17.jpg')
    before_time = perf_counter()
    
    queue.put((image, before_time))
    after_time = perf_counter()
    print(f'enqueing took {(after_time - before_time) * 1000} ms')
    p.join()



if __name__ == '__main__':
    # Create the array
    shared_memory_approach()


