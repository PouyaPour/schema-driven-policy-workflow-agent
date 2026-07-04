.PHONY: install test eval mcp-demo demo check

install:
	python -m pip install --upgrade pip setuptools wheel
	python -m pip install -e ".[dev]"

test:
	python -m pytest -q

eval:
	python eval_runner.py

mcp-demo:
	python mcp/client_demo.py

demo:
	python scripts/demo.py

check: test eval
