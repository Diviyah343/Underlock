from simulator.generator import TrafficGenerator
from worker.consumer import TransactionConsumer


def test_generator_is_seeded_and_emits_all_fraud_patterns() -> None:
    first = TrafficGenerator(seed=23, account_count=40, rate=100, fraud_rate=1)
    second = TrafficGenerator(seed=23, account_count=40, rate=100, fraud_rate=1)
    first_items = [first.generate() for _ in range(200)]
    second_items = [second.generate() for _ in range(200)]

    assert [item.transaction.model_dump_json() for item in first_items] == [
        item.transaction.model_dump_json() for item in second_items
    ]
    assert {item.pattern for item in first_items} == {item.pattern for item in second_items}
    assert {item.pattern.value for item in first_items if item.pattern} == {
        "over_10x_average",
        "new_beneficiary_high_amount",
        "new_device_transfer",
        "multi_hop",
    }


def test_targeted_fraud_patterns_match_worker_alert_rules() -> None:
    generator = TrafficGenerator(seed=23, account_count=40, rate=100, fraud_rate=1)
    matched_rules: set[str] = set()
    for _ in range(200):
        item = generator.generate()
        rule_key = TransactionConsumer._alert_rule_for(item.transaction)
        if rule_key is not None:
            matched_rules.add(rule_key)

    assert matched_rules == {
        "amount-average",
        "new-beneficiary-high-amount",
        "new-device-transfer",
    }
