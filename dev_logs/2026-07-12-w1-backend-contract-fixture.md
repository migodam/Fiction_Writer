# W1 Backend Contract Fixture

- Change: Created `novel.txt` in `test_preaccept_import_stages_manuscript_without_canonical_writes` with the same bytes as `source_text`, satisfying the raw-source evidence contract before `node_write_to_project`.
- Files modified: `tests/test_w1_backend_contract.py` and this log.
- Tests requested: `pytest -q tests/test_w1_backend_contract.py::test_preaccept_import_stages_manuscript_without_canonical_writes`; `pytest -q tests/test_w1_*.py`.
- Result: Not executed because this environment has no `pytest` executable and `python3 -m pytest` reports `No module named pytest`.
