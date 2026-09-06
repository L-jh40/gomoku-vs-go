"""Verify mp.Event can travel through mp.Queue on Windows spawn."""
import multiprocessing as mp


def child(job_q, result_q):
    job = job_q.get()
    ev = job["ev"]
    result_q.put(("got", ev.is_set()))
    ev.wait(timeout=5)
    result_q.put(("set", ev.is_set()))


if __name__ == "__main__":
    ctx = mp.get_context("spawn")
    job_q = ctx.Queue()
    result_q = ctx.Queue()
    ev = ctx.Event()
    job_q.put({"ev": ev})
    p = ctx.Process(target=child, args=(job_q, result_q), daemon=True)
    p.start()
    print("child reports:", result_q.get(timeout=10))
    ev.set()
    print("after set:", result_q.get(timeout=10))
    p.join(timeout=5)
    print("OK")
