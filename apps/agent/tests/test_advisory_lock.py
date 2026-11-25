from worker.db import Database


def test_project_advisory_key_stable_across_calls():
    k1 = Database.project_advisory_key("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
    k2 = Database.project_advisory_key("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
    assert k1 == k2
    assert 0 <= k1 < 2**31


def test_project_advisory_key_differs_by_project():
    a = Database.project_advisory_key("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
    b = Database.project_advisory_key("b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a12")
    assert a != b