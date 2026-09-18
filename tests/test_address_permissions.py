from fastapi.routing import APIRoute

from app.adresses.router import router


def _dependency_names(route: APIRoute) -> set[str]:
    return {dependency.call.__name__ for dependency in route.dependant.dependencies}


def test_address_reads_and_edits_require_regular_user():
    regular_routes = [
        route
        for route in router.routes
        if isinstance(route, APIRoute) and route.methods & {"GET", "POST", "PATCH"}
    ]

    assert regular_routes
    for route in regular_routes:
        assert "get_current_user" in _dependency_names(route)
        assert "get_current_privileged_user" not in _dependency_names(route)


def test_address_delete_keeps_privileged_access():
    delete_routes = [
        route
        for route in router.routes
        if isinstance(route, APIRoute) and "DELETE" in route.methods
    ]

    assert delete_routes
    for route in delete_routes:
        assert "get_current_privileged_user" in _dependency_names(route)
