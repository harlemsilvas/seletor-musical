"""Encerramento de processos e descendentes no Linux."""
import asyncio
import os
import signal


async def terminate(proc):
    if proc.returncode is None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            await asyncio.wait_for(proc.wait(), 3)
        except asyncio.TimeoutError:
            pass
        except ProcessLookupError:
            pass
    # O líder pode sair antes de um descendente que ignora SIGTERM.
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    await proc.wait()
