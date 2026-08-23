from mlops_control_plane.demo import run_demo


def test_demo_release_gate_passes() -> None:
    result = run_demo()
    assert result["release_gate"]["decision"] == "PASS"
    assert result["decisions"]["bad_candidate_v2"]["decision"] == "REJECT"
    assert result["decisions"]["good_candidate_v3"]["decision"] == "PROMOTE"
    assert result["final_production"]["version"] == "v1"
    assert all(result["invariants"].values())
