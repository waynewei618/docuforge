"""允许 python -m src.generate ... 调用。"""
from .generate import main

raise SystemExit(main())
