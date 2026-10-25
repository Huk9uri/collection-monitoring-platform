from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_smartplace_operations_contract_is_documented() -> None:
    operations_text = "\n".join(
        (
            (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8"),
            (
                REPOSITORY_ROOT / "docs" / "운영" / "로컬-실행.md"
            ).read_text(encoding="utf-8"),
            (
                REPOSITORY_ROOT / "docs" / "운영" / "배포-및-장애대응.md"
            ).read_text(encoding="utf-8"),
            (
                REPOSITORY_ROOT / "docs" / "운영" / "smartplace-사후-모니터링.md"
            ).read_text(encoding="utf-8"),
        )
    )

    for token in (
        "SMARTPLACE_COLLECTION_RUN",
        "SMARTPLACE_COLLECTION_ATTEMPT",
        "SELECT 전용",
        "ACCOUNT_PROTECTED",
        "NOT_RUN",
        "ABORTED",
        "대시보드에서 실행하지 않는다",
    ):
        assert token in operations_text
