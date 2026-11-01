"""Seeded PaySim-style traffic and fraud-pattern generation."""

import hashlib
import math
import random
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from shared.constants import FraudPattern, TransactionDirection, TransactionType
from shared.schemas import IngestTransaction

JURISDICTIONS = (("US", "USD"), ("GB", "GBP"), ("SG", "SGD"), ("AU", "AUD"), ("DE", "EUR"))


@dataclass(frozen=True)
class DeviceProfile:
    device_id: UUID
    fingerprint: str


@dataclass(frozen=True)
class BeneficiaryProfile:
    beneficiary_id: UUID
    counterparty_ref: str


@dataclass(frozen=True)
class AccountProfile:
    account_id: UUID
    external_ref: str
    jurisdiction: str
    currency: str
    average_outflow: Decimal
    devices: tuple[DeviceProfile, ...]
    beneficiaries: tuple[BeneficiaryProfile, ...]
    shared_ip: str


@dataclass(frozen=True)
class SimulatedTransaction:
    transaction: IngestTransaction
    is_fraud: bool
    pattern: FraudPattern | None


def stable_uuid(seed: int, identifier: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"underlock-simulator:{seed}:{identifier}")


class TrafficGenerator:
    def __init__(self, seed: int, account_count: int, rate: float, fraud_rate: float) -> None:
        self.seed = seed
        self.rng = random.Random(seed)
        self.rate = rate
        self.fraud_rate = fraud_rate
        self.sequence = 0
        self.pending: deque[SimulatedTransaction] = deque()
        start_hour = self.rng.randrange(24)
        self.clock = datetime(2025, 1, 1, start_hour, tzinfo=UTC)
        self.accounts = [self._make_account(index) for index in range(account_count)]
        self.balances = {
            account.account_id: Decimal(str(self.rng.randint(25_000, 250_000)))
            for account in self.accounts
        }

    def _make_account(self, index: int) -> AccountProfile:
        jurisdiction, currency = JURISDICTIONS[index % len(JURISDICTIONS)]
        account_id = stable_uuid(self.seed, f"account:{index}")
        shared_device_id = stable_uuid(self.seed, f"shared-device:{index // 12}")
        devices = [DeviceProfile(shared_device_id, f"fingerprint:{shared_device_id}")]
        for device_index in range(self.rng.randint(0, 2)):
            device_id = stable_uuid(self.seed, f"device:{index}:{device_index}")
            devices.append(DeviceProfile(device_id, f"fingerprint:{device_id}"))
        beneficiaries = tuple(
            BeneficiaryProfile(
                stable_uuid(self.seed, f"beneficiary:{index}:{beneficiary_index}"),
                f"EXT-{index:05d}-{beneficiary_index:02d}",
            )
            for beneficiary_index in range(self.rng.randint(3, 6))
        )
        average = Decimal(str(round(self.rng.lognormvariate(math.log(6000), 0.55), 2)))
        return AccountProfile(
            account_id=account_id,
            external_ref=f"SIM-{self.seed}-{index:06d}",
            jurisdiction=jurisdiction,
            currency=currency,
            average_outflow=average,
            devices=tuple(devices),
            beneficiaries=beneficiaries,
            shared_ip=f"198.51.100.{(index // 12) % 250 + 1}",
        )

    def generate(self) -> SimulatedTransaction:
        if self.pending:
            return self.pending.popleft()

        if self.rng.random() >= self.fraud_rate:
            return self._normal_transaction()

        pattern = self.rng.choice(tuple(FraudPattern))
        if pattern is FraudPattern.OVER_10X_AVERAGE:
            return self._over_average()
        if pattern is FraudPattern.NEW_BENEFICIARY_HIGH_AMOUNT:
            return self._new_beneficiary()
        if pattern is FraudPattern.NEW_DEVICE_TRANSFER:
            return self._new_device()
        self._multi_hop()
        return self.pending.popleft()

    def _normal_transaction(self) -> SimulatedTransaction:
        account = self.rng.choice(self.accounts)
        destination = self._destination(account)
        tx_type = self.rng.choices(
            tuple(TransactionType), weights=(0.34, 0.32, 0.12, 0.12, 0.10), k=1
        )[0]
        direction = self._direction(tx_type)
        amount = self._typical_amount(account)
        beneficiary = self.rng.choice(account.beneficiaries)
        device = self.rng.choice(account.devices)
        transaction = self._transaction(
            account,
            destination,
            tx_type,
            direction,
            amount,
            self._next_time(),
            beneficiary=beneficiary,
            device=device,
        )
        return SimulatedTransaction(transaction, False, None)

    def _over_average(self) -> SimulatedTransaction:
        account = self.rng.choice(self.accounts)
        destination = self._destination(account)
        amount = (account.average_outflow * Decimal("12.5")).quantize(Decimal("0.01"))
        transaction = self._transaction(
            account,
            destination,
            TransactionType.TRANSFER,
            TransactionDirection.OUTFLOW,
            amount,
            self._next_time(),
            beneficiary=self.rng.choice(account.beneficiaries),
        )
        return SimulatedTransaction(transaction, True, FraudPattern.OVER_10X_AVERAGE)

    def _new_beneficiary(self) -> SimulatedTransaction:
        account = self.rng.choice(self.accounts)
        destination = self._destination(account)
        beneficiary_id = stable_uuid(self.seed, f"new-beneficiary:{self.sequence}")
        created_at = self._next_time()
        transaction = self._transaction(
            account,
            destination,
            TransactionType.TRANSFER,
            TransactionDirection.OUTFLOW,
            Decimal("30000.00"),
            created_at + timedelta(minutes=30),
            beneficiary=BeneficiaryProfile(beneficiary_id, f"NEW-{beneficiary_id.hex[:12]}"),
            beneficiary_created_at=created_at,
        )
        self.clock = max(self.clock, created_at + timedelta(minutes=30, seconds=1))
        return SimulatedTransaction(transaction, True, FraudPattern.NEW_BENEFICIARY_HIGH_AMOUNT)

    def _new_device(self) -> SimulatedTransaction:
        account = self.rng.choice(self.accounts)
        destination = self._destination(account)
        occurred_at = self._next_time()
        device_id = stable_uuid(self.seed, f"never-seen-device:{self.sequence}")
        transaction = self._transaction(
            account,
            destination,
            TransactionType.TRANSFER,
            TransactionDirection.OUTFLOW,
            max(Decimal("1000.00"), self._typical_amount(account)),
            occurred_at,
            beneficiary=self.rng.choice(account.beneficiaries),
            device=DeviceProfile(device_id, f"fingerprint:{device_id}"),
            device_first_seen_at=occurred_at - timedelta(minutes=2),
        )
        return SimulatedTransaction(transaction, True, FraudPattern.NEW_DEVICE_TRANSFER)

    def _multi_hop(self) -> None:
        chain = self.rng.sample(self.accounts, 4)
        start_at = self._next_time()
        amount = Decimal(str(round(self.rng.uniform(12_000, 35_000), 2)))
        group: list[SimulatedTransaction] = []
        for hop in range(3):
            source = chain[hop]
            target = chain[hop + 1]
            hop_amount = (amount * Decimal(str(1 - hop * 0.006))).quantize(Decimal("0.01"))
            transaction = self._transaction(
                source,
                target,
                TransactionType.TRANSFER,
                TransactionDirection.OUTFLOW,
                hop_amount,
                start_at + timedelta(seconds=hop * 30),
                beneficiary=self.rng.choice(source.beneficiaries),
            )
            group.append(SimulatedTransaction(transaction, True, FraudPattern.MULTI_HOP))
        self.pending.extend(group)
        self.clock = max(self.clock, start_at + timedelta(seconds=91))

    def _transaction(
        self,
        account: AccountProfile,
        destination: AccountProfile,
        tx_type: TransactionType,
        direction: TransactionDirection,
        amount: Decimal,
        occurred_at: datetime,
        *,
        beneficiary: BeneficiaryProfile | None = None,
        device: DeviceProfile | None = None,
        beneficiary_created_at: datetime | None = None,
        device_first_seen_at: datetime | None = None,
    ) -> IngestTransaction:
        sequence = self.sequence
        self.sequence += 1
        amount = max(Decimal("0.01"), amount.quantize(Decimal("0.01")))
        old_org = self.balances[account.account_id]
        old_dest = self.balances[destination.account_id]
        if direction is TransactionDirection.OUTFLOW:
            new_org = max(Decimal("0"), old_org - amount)
            new_dest = old_dest + amount
        else:
            new_org = old_org + amount
            new_dest = max(Decimal("0"), old_dest - amount)
        self.balances[account.account_id] = new_org
        self.balances[destination.account_id] = new_dest

        device = device or self.rng.choice(account.devices)
        key = f"sim-{self.seed}-{sequence:012d}"
        tx_hash = hashlib.sha256(key.encode()).hexdigest()
        shared_ip = self.rng.random() < 0.35
        ip_address = account.shared_ip if shared_ip else f"203.0.113.{self.rng.randint(1, 254)}"
        return IngestTransaction(
            idempotency_key=key,
            tx_hash=tx_hash,
            account_id=account.account_id,
            account_external_ref=account.external_ref,
            counterparty_account_id=destination.account_id
            if tx_type in (TransactionType.TRANSFER, TransactionType.PAYMENT)
            else None,
            counterparty_external_ref=destination.external_ref,
            counterparty_jurisdiction=destination.jurisdiction,
            beneficiary_id=beneficiary.beneficiary_id if beneficiary else None,
            beneficiary_ref=beneficiary.counterparty_ref if beneficiary else None,
            beneficiary_created_at=beneficiary_created_at,
            amount=amount,
            currency=account.currency,
            jurisdiction=account.jurisdiction,
            ip_address=ip_address,
            device_id=device.device_id,
            device_fingerprint=device.fingerprint,
            device_first_seen_at=device_first_seen_at,
            direction=direction,
            tx_type=tx_type,
            oldbalance_org=old_org,
            newbalance_org=new_org,
            oldbalance_dest=old_dest,
            newbalance_dest=new_dest,
            occurred_at=occurred_at,
            avg_90d_outflow=account.average_outflow,
        )

    def _destination(self, source: AccountProfile) -> AccountProfile:
        destination = self.rng.choice(self.accounts)
        while destination.account_id == source.account_id:
            destination = self.rng.choice(self.accounts)
        return destination

    def _typical_amount(self, account: AccountProfile) -> Decimal:
        value = self.rng.lognormvariate(math.log(float(account.average_outflow)), 0.7)
        return Decimal(str(round(value, 2)))

    def _direction(self, tx_type: TransactionType) -> TransactionDirection:
        if tx_type in (TransactionType.CASH_OUT, TransactionType.DEBIT):
            return TransactionDirection.OUTFLOW
        if tx_type is TransactionType.CASH_IN:
            return TransactionDirection.INFLOW
        return self.rng.choice(tuple(TransactionDirection))

    def _next_time(self) -> datetime:
        phase = (self.clock.hour - 8) * math.pi / 12
        hourly_factor = max(0.4, 0.9 + 0.5 * math.sin(phase))
        simulated_seconds = 60 / (self.rate * hourly_factor)
        occurred_at = self.clock
        self.clock += timedelta(seconds=simulated_seconds)
        return occurred_at
