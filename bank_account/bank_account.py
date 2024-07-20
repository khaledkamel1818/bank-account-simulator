"""
Bank Account Simulator.

A small, dependency-free banking simulator written in pure Python.
It demonstrates object-oriented design and the SOLID principles:

* ``Transaction``      - an immutable record of one balance change.
* ``Account``          - abstract base class with the shared account logic.
* ``SavingsAccount``   - earns interest and keeps a minimum balance.
* ``CheckingAccount``  - allows an overdraft up to a fixed limit.
* ``Bank``             - opens/closes accounts, moves money between them
                         and reports statistics.

Money is handled with ``decimal.Decimal`` so that amounts such as 0.1 + 0.2
are exact, as they must be in any financial application.

Run this file directly to see a full demonstration::

    python bank_account.py
"""

from __future__ import annotations

import itertools
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import Enum
from typing import Dict, List, Optional, Union

Number = Union[int, float, str, Decimal]

CENT = Decimal("0.01")


# --------------------------------------------------------------------------
# Exceptions
# --------------------------------------------------------------------------

class BankError(Exception):
    """Base class for every error raised by this module."""


class ValidationError(BankError, ValueError):
    """Raised when input data is invalid (bad email, negative amount...)."""


class InsufficientFundsError(BankError):
    """Raised when a withdrawal or transfer exceeds the available funds."""


class AccountNotFoundError(BankError, KeyError):
    """Raised when an account number does not exist in the bank."""

    def __str__(self) -> str:  # KeyError would otherwise wrap it in quotes
        return str(self.args[0]) if self.args else ""


class AccountClosedError(BankError):
    """Raised when an operation is attempted on a closed account."""


# --------------------------------------------------------------------------
# Validation helpers
# --------------------------------------------------------------------------

_EMAIL_PATTERN = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")


def _require_text(value: str, field_name: str) -> str:
    """Return ``value`` stripped, or raise if it is empty or not a string."""
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field_name} must be a non-empty string.")
    return value.strip()


def _validate_email(email: str) -> str:
    """Return a normalized (lower-case) email, or raise if it is malformed."""
    email = _require_text(email, "Email").lower()
    if not _EMAIL_PATTERN.match(email):
        raise ValidationError(f"Invalid email address: {email!r}.")
    return email


def to_money(value: Number, field_name: str = "Amount") -> Decimal:
    """Convert ``value`` to a ``Decimal`` rounded to cents.

    Floats are converted through ``str`` so that ``0.1`` becomes exactly
    ``Decimal("0.10")`` instead of ``0.1000000000000000055...``.
    """
    # bool is a subclass of int, but True/False are never valid amounts.
    if isinstance(value, bool) or not isinstance(
        value, (int, float, str, Decimal)
    ):
        raise ValidationError(f"{field_name} must be a number.")
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        raise ValidationError(f"{field_name} must be a number.") from None
    if not amount.is_finite():
        raise ValidationError(f"{field_name} must be a finite number.")
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def _positive_money(value: Number) -> Decimal:
    """Return ``value`` as money, or raise if it is not strictly positive."""
    amount = to_money(value)
    if amount <= 0:
        raise ValidationError("Amount must be greater than zero.")
    return amount


def format_money(amount: Decimal) -> str:
    """Format an amount as ``$1,234.50`` (negative as ``-$12.00``)."""
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.2f}"


# --------------------------------------------------------------------------
# Transactions
# --------------------------------------------------------------------------

class TransactionType(Enum):
    """The kinds of balance change an account can record."""

    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    TRANSFER_IN = "transfer in"
    TRANSFER_OUT = "transfer out"
    INTEREST = "interest"


_transaction_ids = itertools.count(1)


@dataclass(frozen=True)
class Transaction:
    """An immutable record of one change to an account balance.

    ``amount`` is always positive; ``type`` says whether money came in or
    went out. ``balance_after`` is the balance once the change was applied.
    """

    type: TransactionType
    amount: Decimal
    balance_after: Decimal
    description: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    transaction_id: int = field(default_factory=lambda: next(_transaction_ids))

    @property
    def is_credit(self) -> bool:
        """True when the transaction added money to the account."""
        return self.type in (
            TransactionType.DEPOSIT,
            TransactionType.TRANSFER_IN,
            TransactionType.INTEREST,
        )

    def __str__(self) -> str:
        sign = "+" if self.is_credit else "-"
        text = (
            f"#{self.transaction_id:<4} {self.timestamp:%Y-%m-%d %H:%M}  "
            f"{self.type.value:<12} {sign}{format_money(self.amount):>11}  "
            f"balance {format_money(self.balance_after):>11}"
        )
        return f"{text}  {self.description}" if self.description else text


# --------------------------------------------------------------------------
# Accounts
# --------------------------------------------------------------------------

class Account(ABC):
    """Common behaviour shared by every account type.

    Subclasses decide *how much* may be withdrawn by implementing
    :meth:`available_funds` (Open/Closed principle): the deposit, withdraw
    and history logic below never needs to change for a new account type.
    """

    account_type = "Account"

    def __init__(
        self,
        account_number: str,
        owner: str,
        email: str,
        initial_deposit: Number = 0,
    ) -> None:
        self._account_number = _require_text(account_number, "Account number")
        self._owner = _require_text(owner, "Owner name")
        self._email = _validate_email(email)
        self._balance = Decimal("0.00")
        self._transactions: List[Transaction] = []
        self._is_open = True
        self._opened_on = datetime.now()

        opening = to_money(initial_deposit, "Initial deposit")
        if opening < 0:
            raise ValidationError("Initial deposit cannot be negative.")
        if opening > 0:
            self.deposit(opening, "Opening deposit")

    # -- read-only properties (encapsulation) -----------------------------

    @property
    def account_number(self) -> str:
        """The unique account number."""
        return self._account_number

    @property
    def owner(self) -> str:
        """The account holder's name."""
        return self._owner

    @property
    def email(self) -> str:
        """The account holder's normalized email."""
        return self._email

    @property
    def balance(self) -> Decimal:
        """The current balance. It can only change through transactions."""
        return self._balance

    @property
    def is_open(self) -> bool:
        """False once the account has been closed."""
        return self._is_open

    @property
    def opened_on(self) -> datetime:
        """When the account was opened."""
        return self._opened_on

    @property
    def transactions(self) -> List[Transaction]:
        """A copy of the transaction history, oldest first."""
        return list(self._transactions)

    # -- policy hooks for subclasses -------------------------------------

    @abstractmethod
    def available_funds(self) -> Decimal:
        """How much can be withdrawn right now."""

    # -- operations ------------------------------------------------------

    def deposit(self, amount: Number, description: str = "") -> Transaction:
        """Add money to the account and return the recorded transaction."""
        return self._credit(
            _positive_money(amount), TransactionType.DEPOSIT, description
        )

    def withdraw(self, amount: Number, description: str = "") -> Transaction:
        """Take money out of the account and return the transaction.

        Raises :class:`InsufficientFundsError` when ``amount`` is larger
        than :meth:`available_funds`.
        """
        return self._debit(
            _positive_money(amount), TransactionType.WITHDRAWAL, description
        )

    def close(self) -> None:
        """Close the account. Its balance must be exactly zero."""
        self._ensure_open()
        if self._balance != 0:
            raise BankError(
                f"Account {self.account_number} must have a zero balance "
                f"before closing (current: {format_money(self._balance)})."
            )
        self._is_open = False

    def history(
        self, transaction_type: Optional[TransactionType] = None
    ) -> List[Transaction]:
        """Return the history, optionally filtered by transaction type."""
        if transaction_type is None:
            return self.transactions
        return [t for t in self._transactions if t.type is transaction_type]

    def get_info(self) -> Dict[str, object]:
        """Return a dictionary summary of the account."""
        return {
            "account_number": self.account_number,
            "type": self.account_type,
            "owner": self.owner,
            "email": self.email,
            "balance": self.balance,
            "transactions": len(self._transactions),
            "status": "open" if self.is_open else "closed",
            "opened_on": self.opened_on.strftime("%Y-%m-%d"),
        }

    # -- internals -------------------------------------------------------

    def _ensure_open(self) -> None:
        if not self._is_open:
            raise AccountClosedError(
                f"Account {self.account_number} is closed."
            )

    def _credit(
        self, amount: Decimal, kind: TransactionType, description: str
    ) -> Transaction:
        self._ensure_open()
        self._balance += amount
        return self._record(kind, amount, description)

    def _debit(
        self, amount: Decimal, kind: TransactionType, description: str
    ) -> Transaction:
        self._ensure_open()
        available = self.available_funds()
        if amount > available:
            raise InsufficientFundsError(
                f"Cannot take {format_money(amount)} from account "
                f"{self.account_number}: only {format_money(available)} "
                "available."
            )
        self._balance -= amount
        return self._record(kind, amount, description)

    def _record(
        self, kind: TransactionType, amount: Decimal, description: str
    ) -> Transaction:
        transaction = Transaction(kind, amount, self._balance, description)
        self._transactions.append(transaction)
        return transaction

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(account_number={self.account_number!r}, "
            f"owner={self.owner!r}, balance={format_money(self.balance)})"
        )

    def __str__(self) -> str:
        status = "" if self.is_open else "  [closed]"
        return (
            f"{self.account_number}  {self.account_type:<9} "
            f"{self.owner:<16} {format_money(self.balance):>12}{status}"
        )


class SavingsAccount(Account):
    """An account that earns interest and keeps a minimum balance."""

    account_type = "Savings"

    def __init__(
        self,
        account_number: str,
        owner: str,
        email: str,
        initial_deposit: Number = 0,
        interest_rate: Number = "0.02",
        minimum_balance: Number = 0,
    ) -> None:
        try:
            if isinstance(interest_rate, bool):
                raise InvalidOperation
            rate = Decimal(str(interest_rate))
        except InvalidOperation:
            raise ValidationError("Interest rate must be a number.") from None
        if not rate.is_finite() or not Decimal(0) <= rate <= Decimal(1):
            raise ValidationError("Interest rate must be between 0 and 1.")
        minimum = to_money(minimum_balance, "Minimum balance")
        if minimum < 0:
            raise ValidationError("Minimum balance cannot be negative.")
        self._interest_rate = rate
        self._minimum_balance = minimum
        super().__init__(account_number, owner, email, initial_deposit)

    @property
    def interest_rate(self) -> Decimal:
        """Interest rate applied by :meth:`apply_interest` (0.02 = 2%)."""
        return self._interest_rate

    @property
    def minimum_balance(self) -> Decimal:
        """The balance may never drop below this amount."""
        return self._minimum_balance

    def available_funds(self) -> Decimal:
        return max(self._balance - self._minimum_balance, Decimal("0.00"))

    def apply_interest(self) -> Optional[Transaction]:
        """Credit one period of interest. Returns None if it rounds to 0."""
        interest = (self._balance * self._interest_rate).quantize(
            CENT, rounding=ROUND_HALF_UP
        )
        if interest <= 0:
            return None
        return self._credit(
            interest,
            TransactionType.INTEREST,
            f"Interest at {self._interest_rate:.2%}",
        )

    def get_info(self) -> Dict[str, object]:
        info = super().get_info()
        info["interest_rate"] = f"{self.interest_rate:.2%}"
        info["minimum_balance"] = self.minimum_balance
        return info


class CheckingAccount(Account):
    """An everyday account that may go negative up to an overdraft limit."""

    account_type = "Checking"

    def __init__(
        self,
        account_number: str,
        owner: str,
        email: str,
        initial_deposit: Number = 0,
        overdraft_limit: Number = 0,
    ) -> None:
        limit = to_money(overdraft_limit, "Overdraft limit")
        if limit < 0:
            raise ValidationError("Overdraft limit cannot be negative.")
        self._overdraft_limit = limit
        super().__init__(account_number, owner, email, initial_deposit)

    @property
    def overdraft_limit(self) -> Decimal:
        """How far below zero the balance may go."""
        return self._overdraft_limit

    def available_funds(self) -> Decimal:
        return self._balance + self._overdraft_limit

    def get_info(self) -> Dict[str, object]:
        info = super().get_info()
        info["overdraft_limit"] = self.overdraft_limit
        return info


# --------------------------------------------------------------------------
# Bank
# --------------------------------------------------------------------------

class Bank:
    """Stores accounts and provides account management, transfers and
    statistics.

    The bank depends only on the abstract :class:`Account` interface
    (Dependency Inversion), so any new account type works here unchanged.
    """

    def __init__(self, name: str) -> None:
        self._name = _require_text(name, "Bank name")
        self._accounts: Dict[str, Account] = {}
        self._next_number = itertools.count(1001)

    @property
    def name(self) -> str:
        """The bank's display name."""
        return self._name

    def __len__(self) -> int:
        return len(self._accounts)

    def __contains__(self, account_number: object) -> bool:
        return account_number in self._accounts

    # -- account management (CRUD) ---------------------------------------

    def _new_account_number(self) -> str:
        return f"ACC-{next(self._next_number)}"

    def open_savings_account(
        self,
        owner: str,
        email: str,
        initial_deposit: Number = 0,
        interest_rate: Number = "0.02",
        minimum_balance: Number = 0,
    ) -> SavingsAccount:
        """Open a savings account and return it."""
        account = SavingsAccount(
            self._new_account_number(),
            owner,
            email,
            initial_deposit,
            interest_rate,
            minimum_balance,
        )
        return self._register(account)

    def open_checking_account(
        self,
        owner: str,
        email: str,
        initial_deposit: Number = 0,
        overdraft_limit: Number = 0,
    ) -> CheckingAccount:
        """Open a checking account and return it."""
        account = CheckingAccount(
            self._new_account_number(),
            owner,
            email,
            initial_deposit,
            overdraft_limit,
        )
        return self._register(account)

    def _register(self, account: Account) -> Account:
        if account.account_number in self._accounts:
            raise BankError(
                f"Account number {account.account_number} already exists."
            )
        self._accounts[account.account_number] = account
        return account

    def get_account(self, account_number: str) -> Account:
        """Return the account, or raise :class:`AccountNotFoundError`."""
        try:
            return self._accounts[account_number]
        except KeyError:
            raise AccountNotFoundError(
                f"No account with number {account_number!r}."
            ) from None

    def close_account(self, account_number: str) -> Account:
        """Close an account (its balance must be zero) and return it.

        Closed accounts are kept so their history stays available.
        """
        account = self.get_account(account_number)
        account.close()
        return account

    def find_accounts_by_owner(self, owner: str) -> List[Account]:
        """Return every account whose owner name matches (case-insensitive)."""
        wanted = _require_text(owner, "Owner name").casefold()
        return [
            a for a in self._accounts.values() if a.owner.casefold() == wanted
        ]

    def list_accounts(self, include_closed: bool = False) -> List[Account]:
        """Return accounts in the order they were opened."""
        return [
            a for a in self._accounts.values() if include_closed or a.is_open
        ]

    # -- money movement --------------------------------------------------

    def deposit(self, account_number: str, amount: Number) -> Transaction:
        """Deposit into the given account."""
        return self.get_account(account_number).deposit(amount)

    def withdraw(self, account_number: str, amount: Number) -> Transaction:
        """Withdraw from the given account."""
        return self.get_account(account_number).withdraw(amount)

    def transfer(
        self, from_number: str, to_number: str, amount: Number
    ) -> None:
        """Move money between two accounts.

        The transfer is all-or-nothing: every check runs before either
        balance changes, so a failed transfer leaves both accounts intact.
        """
        if from_number == to_number:
            raise ValidationError("Cannot transfer to the same account.")
        source = self.get_account(from_number)
        target = self.get_account(to_number)
        value = _positive_money(amount)
        # Check the receiving side first; the debit below does its own
        # checks and raises before touching any balance.
        target._ensure_open()  # noqa: SLF001 - same-module collaborator
        source._debit(  # noqa: SLF001
            value, TransactionType.TRANSFER_OUT, f"To {to_number}"
        )
        target._credit(  # noqa: SLF001
            value, TransactionType.TRANSFER_IN, f"From {from_number}"
        )

    def apply_monthly_interest(self) -> Decimal:
        """Apply interest to every open savings account; return the total."""
        total = Decimal("0.00")
        for account in self.list_accounts():
            if isinstance(account, SavingsAccount):
                transaction = account.apply_interest()
                if transaction is not None:
                    total += transaction.amount
        return total

    # -- reporting -------------------------------------------------------

    def get_richest_accounts(self, n: int = 3) -> List[Account]:
        """Return the ``n`` open accounts with the highest balance."""
        if isinstance(n, bool) or not isinstance(n, int) or n < 1:
            raise ValidationError("n must be a positive integer.")
        return sorted(
            self.list_accounts(), key=lambda a: a.balance, reverse=True
        )[:n]

    def get_statistics(self) -> Dict[str, object]:
        """Return a summary of the whole bank."""
        open_accounts = self.list_accounts()
        balances = [a.balance for a in open_accounts]
        transactions = [
            t for a in self._accounts.values() for t in a.transactions
        ]

        def total_of(*kinds: TransactionType) -> Decimal:
            return sum(
                (t.amount for t in transactions if t.type in kinds),
                Decimal("0.00"),
            )

        by_type: Dict[str, int] = {}
        for account in open_accounts:
            by_type[account.account_type] = (
                by_type.get(account.account_type, 0) + 1
            )

        total = sum(balances, Decimal("0.00"))
        return {
            "total_accounts": len(self._accounts),
            "open_accounts": len(open_accounts),
            "closed_accounts": len(self._accounts) - len(open_accounts),
            "accounts_by_type": by_type,
            "total_deposits_held": total,
            "average_balance": (
                (total / len(balances)).quantize(CENT) if balances else None
            ),
            "highest_balance": max(balances) if balances else None,
            "lowest_balance": min(balances) if balances else None,
            "overdrawn_accounts": sum(1 for b in balances if b < 0),
            "total_transactions": len(transactions),
            "total_deposited": total_of(TransactionType.DEPOSIT),
            "total_withdrawn": total_of(TransactionType.WITHDRAWAL),
            "total_transferred": total_of(TransactionType.TRANSFER_OUT),
            "total_interest_paid": total_of(TransactionType.INTEREST),
        }

    def display_all_accounts(self, include_closed: bool = True) -> None:
        """Print a table of accounts."""
        accounts = self.list_accounts(include_closed)
        print(f"{self.name} - {len(accounts)} account(s)")
        print("-" * 60)
        if not accounts:
            print("No accounts.")
        for account in accounts:
            print(account)
        print("-" * 60)


# --------------------------------------------------------------------------
# Demonstration
# --------------------------------------------------------------------------

def _section(title: str) -> None:
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def _show(value: object) -> str:
    return format_money(value) if isinstance(value, Decimal) else str(value)


def main() -> None:
    """Walk through every feature of the simulator."""
    bank = Bank("Python Community Bank")

    _section("1. Opening accounts")
    alice_savings = bank.open_savings_account(
        "Alice Johnson", "alice@example.com", 5000,
        interest_rate="0.015", minimum_balance=500,
    )
    alice_checking = bank.open_checking_account(
        "Alice Johnson", "alice@example.com", 1200, overdraft_limit=300
    )
    bob = bank.open_checking_account("Bob Smith", "bob@example.com", 800)
    carol = bank.open_savings_account(
        "Carol White", "carol@example.com", 12000, interest_rate="0.02"
    )
    dave = bank.open_checking_account("Dave Brown", "dave@example.com")
    for account in bank.list_accounts():
        print(f"Opened {account!r}")

    _section("2. Deposits and withdrawals")
    print(bob.deposit(450.75, "Salary"))
    print(bob.withdraw(120, "Groceries"))
    print(alice_checking.withdraw(1350, "Rent (uses overdraft)"))
    print(f"Alice's checking balance: {format_money(alice_checking.balance)}")
    print("Precise money: 0.1 + 0.2 deposited -> ", end="")
    dave.deposit(0.1)
    dave.deposit(0.2)
    print(format_money(dave.balance))

    _section("3. Transfers")
    bank.transfer(carol.account_number, bob.account_number, 2500)
    bank.transfer(alice_savings.account_number,
                  alice_checking.account_number, 1000)
    print("Carol -> Bob: $2,500.00")
    print("Alice savings -> Alice checking: $1,000.00")
    print(f"Bob now has {format_money(bob.balance)}")

    _section("4. Interest")
    paid = bank.apply_monthly_interest()
    print(f"Interest paid to savings accounts: {format_money(paid)}")

    _section("5. Error handling")
    attempts = [
        ("Withdraw more than available",
         lambda: bob.withdraw(1_000_000)),
        ("Go below the savings minimum balance",
         lambda: alice_savings.withdraw(alice_savings.balance)),
        ("Deposit a negative amount", lambda: bob.deposit(-50)),
        ("Deposit a non-number", lambda: bob.deposit("ten")),
        ("Transfer to an unknown account",
         lambda: bank.transfer(bob.account_number, "ACC-9999", 10)),
        ("Transfer to the same account",
         lambda: bank.transfer(bob.account_number, bob.account_number, 10)),
        ("Open an account with a bad email",
         lambda: bank.open_checking_account("Eve", "not-an-email")),
        ("Close an account that still has money",
         lambda: bank.close_account(bob.account_number)),
    ]
    for label, attempt in attempts:
        try:
            attempt()
        except BankError as error:
            print(f"[{type(error).__name__}] {label}: {error}")

    balance_before = carol.balance
    try:
        bank.transfer(carol.account_number, bob.account_number, 10**9)
    except InsufficientFundsError:
        pass
    assert carol.balance == balance_before, "failed transfer changed balance"
    print("A failed transfer left both balances unchanged.")

    _section("6. Closing an account")
    dave.withdraw(dave.balance)
    bank.close_account(dave.account_number)
    print(f"{dave.account_number} closed: {not dave.is_open}")
    try:
        dave.deposit(10)
    except AccountClosedError as error:
        print(f"[AccountClosedError] {error}")

    _section("7. Transaction history")
    print(f"Bob Smith ({bob.account_number}):")
    for transaction in bob.history():
        print(" ", transaction)
    print("\nOnly Bob's withdrawals:")
    for transaction in bob.history(TransactionType.WITHDRAWAL):
        print(" ", transaction)

    _section("8. Account details")
    for key, value in alice_savings.get_info().items():
        print(f"  {key:<16}: {_show(value)}")
    owned = bank.find_accounts_by_owner("alice johnson")
    print(f"\nAlice Johnson owns {len(owned)} account(s).")

    _section("9. All accounts")
    bank.display_all_accounts()

    _section("10. Richest accounts")
    for rank, account in enumerate(bank.get_richest_accounts(3), start=1):
        print(f"{rank}. {account.owner:<16} {format_money(account.balance)}")

    _section("11. Bank statistics")
    for key, value in bank.get_statistics().items():
        print(f"  {key:<22}: {_show(value)}")


if __name__ == "__main__":
    main()
