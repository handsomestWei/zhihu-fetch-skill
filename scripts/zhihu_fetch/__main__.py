"""python -m zhihu_fetch <命令>

从技能根目录: PYTHONPATH=scripts python -m zhihu_fetch route <URL>
更推荐: python scripts/zhihu.py route <URL>
"""
import os
import sys

_SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from zhihu import main

if __name__ == "__main__":
    main()
