"""Allow running the server via ``python -m flextoolsmcp``."""

if __package__:
    from .server import run
else:
    from server import run

if __name__ == "__main__":
    run()
