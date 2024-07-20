# Bank Account Simulator

A clean, object-oriented banking simulator written in **pure Python**
(standard library only). It opens savings and checking accounts, handles
deposits, withdrawals and transfers, pays interest, keeps a full transaction
history for every account and reports bank-wide statistics, with input
validation and clear error handling throughout.

## Features

- **Two account types**: savings (interest and minimum balance) and checking
  (optional overdraft limit), built on one abstract `Account` class.
- **Account management**: open, look up, search by owner, list and close
  accounts. Closed accounts keep their history.
- **Deposits and withdrawals**: amounts validated and rounded to cents.
- **Transfers**: all-or-nothing; a failed transfer never changes a balance.
- **Exact money**: `decimal.Decimal` everywhere, so `0.1 + 0.2` is `0.30`.
- **Transaction history**: immutable records with type, amount, running
  balance, timestamp and description, filterable by type.
- **Interest**: monthly interest for every savings account in one call.
- **Statistics**: totals, average, highest and lowest balance, overdrawn
  accounts, money deposited, withdrawn, transferred and paid as interest.
- **Validation and errors**: a custom exception hierarchy for invalid data,
  insufficient funds, unknown accounts and closed accounts.
- **Zero dependencies**: runs anywhere Python 3.8+ is installed.

## Project structure

```
bank_account/
├── bank_account.py    # Classes and a runnable demonstration
├── README.md          # This file
└── requirements.txt   # No external dependencies
```

## Installation

```bash
git clone https://github.com/khaledkamel1818/bank-account-simulator.git
cd bank-account-simulator/bank_account
```

No `pip install` is needed. `requirements.txt` lists no packages.

## Usage

Run the full demonstration:

```bash
python bank_account.py
```

Or use the classes in your own code:

```python
from bank_account import Bank, InsufficientFundsError, TransactionType

bank = Bank("My Bank")

# Open accounts
savings = bank.open_savings_account(
    "Alice Johnson", "alice@example.com", 5000,
    interest_rate="0.015", minimum_balance=500,
)
checking = bank.open_checking_account(
    "Bob Smith", "bob@example.com", 800, overdraft_limit=200,
)

# Move money
checking.deposit(450.75, "Salary")
checking.withdraw(120, "Groceries")
bank.transfer(savings.account_number, checking.account_number, 1000)
bank.apply_monthly_interest()

# Query
print(checking.balance)                         # 2130.75
for t in checking.history(TransactionType.WITHDRAWAL):
    print(t)
print(bank.get_richest_accounts(3))
print(bank.get_statistics())

# Errors are explicit and catchable
try:
    checking.withdraw(1_000_000)
except InsufficientFundsError as error:
    print(error)

# Close an account (balance must be zero first)
checking.withdraw(checking.balance)
bank.close_account(checking.account_number)
```

Amounts can be given as `int`, `float`, `str` or `Decimal`; they are always
stored as `Decimal` rounded to cents.

## Classes and methods

### `Transaction` (immutable value object)

| Member | Description |
| --- | --- |
| `type` | A `TransactionType`: deposit, withdrawal, transfer in/out, interest |
| `amount`, `balance_after` | The amount (always positive) and the balance afterwards |
| `description`, `timestamp`, `transaction_id` | Details of the record |
| `is_credit` | `True` when money came into the account |

### `Account` (abstract base class)

| Member | Description |
| --- | --- |
| `account_number`, `owner`, `email`, `balance`, `is_open`, `opened_on` | Read-only properties |
| `deposit(amount, description="")` | Add money; returns the `Transaction` |
| `withdraw(amount, description="")` | Take money out; raises `InsufficientFundsError` past the limit |
| `available_funds()` | **Abstract**: how much can be withdrawn now |
| `history(transaction_type=None)` | Transaction list, optionally filtered |
| `get_info()` | Dictionary summary of the account |
| `close()` | Close the account; the balance must be zero |

### `SavingsAccount(Account)`

Adds `interest_rate` (for example `0.02` for 2%) and `minimum_balance`.
`available_funds()` is the balance above the minimum, and
`apply_interest()` credits one period of interest.

### `CheckingAccount(Account)`

Adds `overdraft_limit`. `available_funds()` is the balance plus the
overdraft, so the balance may go negative down to `-overdraft_limit`.

### `Bank`

| Method | Description |
| --- | --- |
| `open_savings_account(...)`, `open_checking_account(...)` | Open an account with an auto-generated number (`ACC-1001`, ...) |
| `get_account(number)` | Look up an account |
| `find_accounts_by_owner(owner)` | All accounts of one owner (case-insensitive) |
| `list_accounts(include_closed=False)` | Accounts in opening order |
| `close_account(number)` | Close an account with a zero balance |
| `deposit(number, amount)`, `withdraw(number, amount)` | Shortcuts by account number |
| `transfer(from_number, to_number, amount)` | All-or-nothing transfer |
| `apply_monthly_interest()` | Pay interest on all savings accounts; returns the total |
| `get_richest_accounts(n=3)` | The `n` highest open balances |
| `get_statistics()` | Dictionary of bank-wide statistics |
| `display_all_accounts()` | Print a table of every account |

### Exceptions

```
BankError
├── ValidationError         (also a ValueError)
├── InsufficientFundsError
├── AccountNotFoundError    (also a KeyError)
└── AccountClosedError
```

Catch `BankError` to handle every error from this module in one place.

## OOP concepts used

- **Encapsulation**: the balance and history are private and exposed
  through read-only properties; they change only through `deposit`,
  `withdraw` and transfers, which always record a transaction.
- **Abstraction**: `Account` is an abstract base class; callers work with
  `deposit`, `withdraw` and `history` without knowing the account type.
- **Inheritance**: `SavingsAccount` and `CheckingAccount` reuse all of
  `Account` and add only what is specific to them.
- **Polymorphism**: each subclass answers `available_funds()` differently,
  and the same `withdraw` code enforces a minimum balance or an overdraft.
- **Composition**: a `Bank` holds accounts, and an account holds its
  `Transaction` records.
- **Value objects**: `Transaction` is a frozen dataclass and cannot be
  altered after it is recorded.

### SOLID principles

- **Single Responsibility**: `Transaction` records, `Account` manages one
  balance, `Bank` coordinates many accounts, and validation lives in small
  helper functions.
- **Open/Closed**: a new account type (for example a fixed deposit) only
  implements `available_funds()`; no existing class changes.
- **Liskov Substitution**: any `Account` subclass can be used wherever an
  `Account` is expected, by the `Bank` or by your own code.
- **Interface Segregation**: subclasses implement just one abstract method;
  extra behaviour such as `apply_interest()` lives only where it belongs.
- **Dependency Inversion**: `Bank` depends on the abstract `Account`
  interface, not on concrete account classes, for deposits, withdrawals,
  transfers and reports.

## Expected output

Running `python bank_account.py` prints eleven sections. An excerpt
(timestamps will show the current date and time):

```
1. Opening accounts
Opened SavingsAccount(account_number='ACC-1001', owner='Alice Johnson', balance=$5,000.00)
Opened CheckingAccount(account_number='ACC-1002', owner='Alice Johnson', balance=$1,200.00)
Opened CheckingAccount(account_number='ACC-1003', owner='Bob Smith', balance=$800.00)
Opened SavingsAccount(account_number='ACC-1004', owner='Carol White', balance=$12,000.00)
Opened CheckingAccount(account_number='ACC-1005', owner='Dave Brown', balance=$0.00)

2. Deposits and withdrawals
#5    YYYY-MM-DD HH:MM  deposit      +    $450.75  balance   $1,250.75  Salary
#6    YYYY-MM-DD HH:MM  withdrawal   -    $120.00  balance   $1,130.75  Groceries
#7    YYYY-MM-DD HH:MM  withdrawal   -  $1,350.00  balance    -$150.00  Rent (uses overdraft)
Alice's checking balance: -$150.00
Precise money: 0.1 + 0.2 deposited -> $0.30
...

5. Error handling
[InsufficientFundsError] Withdraw more than available: Cannot take $1,000,000.00 from account ACC-1003: only $3,630.75 available.
[InsufficientFundsError] Go below the savings minimum balance: Cannot take $4,060.00 from account ACC-1001: only $3,560.00 available.
[ValidationError] Deposit a negative amount: Amount must be greater than zero.
[ValidationError] Deposit a non-number: Amount must be a number.
[AccountNotFoundError] Transfer to an unknown account: No account with number 'ACC-9999'.
[ValidationError] Transfer to the same account: Cannot transfer to the same account.
[ValidationError] Open an account with a bad email: Invalid email address: 'not-an-email'.
[BankError] Close an account that still has money: Account ACC-1003 must have a zero balance before closing (current: $3,630.75).
A failed transfer left both balances unchanged.
...

9. All accounts
Python Community Bank - 5 account(s)
------------------------------------------------------------
ACC-1001  Savings   Alice Johnson       $4,060.00
ACC-1002  Checking  Alice Johnson         $850.00
ACC-1003  Checking  Bob Smith           $3,630.75
ACC-1004  Savings   Carol White         $9,690.00
ACC-1005  Checking  Dave Brown              $0.00  [closed]
------------------------------------------------------------

10. Richest accounts
1. Carol White      $9,690.00
2. Alice Johnson    $4,060.00
3. Bob Smith        $3,630.75

11. Bank statistics
  total_accounts        : 5
  open_accounts         : 4
  closed_accounts       : 1
  accounts_by_type      : {'Savings': 2, 'Checking': 2}
  total_deposits_held   : $18,230.75
  average_balance       : $4,557.69
  highest_balance       : $9,690.00
  lowest_balance        : $850.00
  overdrawn_accounts    : 0
  total_transactions    : 16
  total_deposited       : $19,451.05
  total_withdrawn       : $1,470.30
  total_transferred     : $3,500.00
  total_interest_paid   : $250.00
```

## Author

**Khaled Kamel** · [GitHub](https://github.com/khaledkamel1818)
