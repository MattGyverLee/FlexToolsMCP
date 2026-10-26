"""Allow running the server via ``python -m flextoolsmcp``."""

try:
    from .server import run
except ImportError as _first_exc:
    try:
        from server import run
    except ImportError as _second_exc:
        raise _second_exc from _first_exc

if __name__ == "__main__":
    run()
