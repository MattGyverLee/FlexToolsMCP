"""Allow running the server via ``python -m flextoolsmcp``."""

if __package__:
    try:
        from .server import run
    except ImportError as _first_exc:
        try:
            from server import run
        except ImportError as _second_exc:
            raise _second_exc from _first_exc
else:
    from server import run

if __name__ == "__main__":
    run()
