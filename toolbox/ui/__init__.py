def __getattr__(name):
    if name == "MainWindow":
        from .main_window import MainWindow
        return MainWindow
    elif name == "HomePage":
        from .home_page import HomePage
        return HomePage
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["MainWindow", "HomePage"]

