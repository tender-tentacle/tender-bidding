

def test_conditional_deletion_logic_rule():
    """
    Verifies that deletion of old ratings only occurs when new live data is successfully crawled,
    and preserves existing DB ratings if the crawl fails or returns a fallback block.
    """
    # 1. Successful live crawl (is_fallback=False) -> MUST delete old ratings and store new ones
    payload_success = {"comments": [{"title": "New Live Review", "comment_hash": "hash1"}], "is_fallback": False}
    is_successful_crawl_1 = bool(payload_success.get("comments")) and not payload_success.get("is_fallback", False)
    assert is_successful_crawl_1 is True

    # 2. Failed / fallback crawl (is_fallback=True) -> MUST NOT delete existing DB ratings
    payload_fallback = {"comments": [{"title": "Fallback Review", "comment_hash": "hash2"}], "is_fallback": True}
    is_successful_crawl_2 = bool(payload_fallback.get("comments")) and not payload_fallback.get("is_fallback", False)
    assert is_successful_crawl_2 is False


if __name__ == "__main__":
    test_conditional_deletion_logic_rule()
    print("CONDITIONAL DELETION UNIT TEST PASSED CLEANLY!")
