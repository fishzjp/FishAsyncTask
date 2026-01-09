"""FishAsyncTask 性能优化构建脚本

支持 Cython 扩展的编译和安装。
"""

from setuptools import setup, Extension
from setuptools.command.build_py import build_py
from Cython.Build import cythonize
import sys
from pathlib import Path

# Cython 扩展模块
cython_extensions = [
    Extension(
        "fish_async_task._cython._sharded_status",
        ["fish_async_task/_cython/_sharded_status.pyx"],
        include_dirs=[str(Path(__file__).parent)],
    ),
    Extension(
        "fish_async_task._cython._priority_queue",
        ["fish_async_task/_cython/_priority_queue.pyx"],
        include_dirs=[str(Path(__file__).parent)],
    ),
]

# 自定义 build_py 命令，支持可选的 Cython 编译
class BuildPyCommand(build_py):
    """自定义构建命令，支持 Cython 可选编译"""

    def run(self):
        # 尝试编译 Cython 扩展
        try:
            import Cython
            cythonize(
                cython_extensions,
                compiler_directives={
                    'language_level': '3',
                    'embedsignature': True,
                }
            )
        except ImportError:
            print("Cython 未安装，跳过 Cython 扩展编译")
            print("将使用纯 Python 实现")

        # 运行标准的 build_py
        build_py.run(self)


setup(
    name="fish_async_task",
    use_scm_version=False,
    cmdclass={
        'build_py': BuildPyCommand,
    },
    ext_modules=cython_extensions,
)
