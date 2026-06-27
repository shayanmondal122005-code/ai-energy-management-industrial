"""Multi-tenant isolation — a user may only access facilities in their own scope.
This is the guard the optimizer endpoint (and every facility endpoint) enforces via
`current_user.can_access_facility(...)`. Proves tenant A cannot read tenant B's data.
(Runs in CI; imports FastAPI-backed security module.)"""
from uuid import uuid4

from backend.core.security import CurrentUser


class TestTenantIsolation:

    def test_user_can_access_own_facility(self):
        fid = uuid4()
        u = CurrentUser(uuid4(), uuid4(), "operator", [str(fid)])
        assert u.can_access_facility(fid) is True

    def test_user_cannot_access_other_tenants_facility(self):
        a_fac = uuid4()
        b_fac = uuid4()                                  # belongs to a different tenant
        a_user = CurrentUser(uuid4(), uuid4(), "operator", [str(a_fac)])
        assert a_user.can_access_facility(b_fac) is False  # cross-tenant read denied

    def test_super_admin_sees_all(self):
        u = CurrentUser(uuid4(), uuid4(), "super_admin", [])
        assert u.can_access_facility(uuid4()) is True
