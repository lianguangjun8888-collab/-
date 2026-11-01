import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
from PySide6.QtCore import QThread,Signal


class AsyncWorker(QThread):
    success = Signal(object)
    failed = Signal(str)

    def __init__(self, work, parent=None):
        super().__init__(parent)
        self.work = work
        self.loop = None
        self.task = None
        self.cancel_requested = False

    def run(self):
        self.loop = asyncio.new_event_loop()
        try:
            self.task = self.loop.create_task(self.work())
            if self.cancel_requested:
                self.task.cancel()
            self.success.emit(self.loop.run_until_complete(self.task))
        except asyncio.CancelledError:
            self.failed.emit('任务已取消')
        except Exception as exc:
            # Ollama errors are already sanitized. Never display raw remote bodies.
            from .ai import AIError
            self.failed.emit(str(exc) if isinstance(exc,(AIError,ValueError)) else '操作失败，请检查本地服务或检测环境。')
        finally:
            self.loop.run_until_complete(self.loop.shutdown_asyncgens())
            self.loop.close()

    def cancel(self):
        self.cancel_requested = True
        if self.loop and self.loop.is_running() and self.task:
            self.loop.call_soon_threadsafe(self.task.cancel)


async def diagnostic_process(include_names=False):
    args = [sys.executable]
    if not getattr(sys,'frozen',False):
        args += ['-m','qianniu_assistant']
    args += ['--diagnose']
    if include_names:
        args += ['--include-names']
    env = os.environ.copy()
    if not getattr(sys,'frozen',False):
        env['PYTHONPATH'] = str(Path(__file__).resolve().parents[1])
    flags = {'creationflags':0x08000000} if sys.platform == 'win32' else {}
    # PyInstaller --windowed has no reliable standard streams on Windows.
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory)/'report.json'
        proc = await asyncio.create_subprocess_exec(*args,'--output',str(output),env=env,
            stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL,**flags)
        try:
            await asyncio.wait_for(proc.wait(),30)
            if proc.returncode != 0 or not output.is_file():
                raise ValueError('检测子进程失败；请检查 Windows 依赖。')
            return json.loads(output.read_text(encoding='utf-8'))
        except asyncio.TimeoutError:
            raise ValueError('检测超过 30 秒，请关闭阻塞的客户端窗口后重试。') from None
        finally:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
