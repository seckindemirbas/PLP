"""
Classes for calling functions a schedule. Has time zone support.

For example, to run a job at 08:00 every morning in 'Asia/Calcutta':

>>> import zoneinfo
>>> job = lambda: print("time is now", datetime.datetime())
>>> time = datetime.time(8, tzinfo=zoneinfo.ZoneInfo('Asia/Calcutta'))
>>> cmd = PeriodicCommandFixedDelay.daily_at(time, job)
>>> print(cmd)
PeriodicCommandFixedDelay: <function <lambda> at ...> at 2...T08:00:00+05:30
>>> sched = InvokeScheduler()
>>> sched.add(cmd)
>>> while True:  # doctest: +SKIP
...     sched.run_pending()
...     time.sleep(.1)

By default, the scheduler uses timezone-aware times in UTC. A
client may override the default behavior by overriding ``now``
and ``from_timestamp`` functions.

>>> now()
datetime.datetime(...utc)
>>> from_timestamp(1718723533.7685602)
datetime.datetime(...utc)

Consumers may supply custom attributes to a command and those
should be retained.

>>> cmd = PeriodicCommandFixedDelay.daily_at(time, job)
>>> cmd.name = 'my task name'
>>> cmd.next().name
'my task name'

Alternatively, to associate custom context (such as a name) with
a command, implement the target as a callable class whose
``__str__`` describes it. The name then naturally carries through
``next()`` as part of the target itself:

>>> class NamedTask:
...     def __init__(self, name, func):
...         self.name = name
...         self.func = func
...     def __str__(self):
...         return self.name
...     def __call__(self):
...         return self.func()
>>> cmd = PeriodicCommandFixedDelay.daily_at(time, NamedTask('my task name', job))
>>> print(cmd)
PeriodicCommandFixedDelay: my task name at 2...T08:00:00+05:30

To bind arguments to the target function, use ``functools.partial``:

>>> import functools
>>> def greet(whom): print(f"Hello, {whom}!")
>>> cmd = PeriodicCommandFixedDelay.daily_at(time, functools.partial(greet, 'world'))
>>> cmd.target()
Hello, world!
"""

from __future__ import annotations

import abc
import bisect
import collections.abc
import datetime
import numbers
from typing import TYPE_CHECKING, Any

from jaraco.collections import set_defaults
from jaraco.context import suppress
from jaraco.functools import passthrough  # type: ignore[attr-defined]

from .utc import fromtimestamp as from_timestamp
from .utc import now as now

if TYPE_CHECKING:
    from typing_extensions import Self


class DelayedCommand(datetime.datetime):
    """
    A command to be executed after some delay (seconds or timedelta).
    """

    delay: datetime.timedelta = datetime.timedelta()
    target: Any  # Expected type depends on the scheduler used

    @classmethod
    def from_datetime(cls, other: datetime.datetime) -> Self:
        return cls(
            other.year,
            other.month,
            other.day,
            other.hour,
            other.minute,
            other.second,
            other.microsecond,
            other.tzinfo,
        )

    @classmethod
    def after(cls, delay: datetime.timedelta | float, target: Any) -> Self:
        if not isinstance(delay, datetime.timedelta):
            delay = datetime.timedelta(seconds=delay)
        due_time = now() + delay
        cmd = cls.from_datetime(due_time)
        cmd.delay = delay
        cmd.target = target
        return cmd

    @staticmethod
    def _from_timestamp(input: datetime.datetime | float) -> datetime.datetime:
        """
        If input is a real number, interpret it as a Unix timestamp
        (seconds sinc Epoch in UTC) and return a timezone-aware
        datetime object. Otherwise return input unchanged.
        """
        if isinstance(input, datetime.datetime):
            return input
        return from_timestamp(input)

    @classmethod
    def at_time(cls, at: datetime.datetime | float, target: Any) -> Self:
        """
        Construct a DelayedCommand to come due at `at`, where `at` may be
        a datetime or timestamp.
        """
        at = cls._from_timestamp(at)
        cmd = cls.from_datetime(at)
        cmd.delay = at - now()
        cmd.target = target
        return cmd

    def due(self) -> bool:
        return now() >= self

    def __str__(self) -> str:
        return f"{self.__class__.__name__}: {self.target} at {self.isoformat()}"


class PeriodicCommand(DelayedCommand):
    """
    Like a delayed command, but expect this command to run every delay
    seconds.
    """

    def _next_time(self) -> Self:
        """
        Add delay to self, localized
        """
        return self + self.delay

    @passthrough  # type: ignore[untyped-decorator]
    @suppress(TypeError)
    def _reflect(self, other: Any) -> Self:  # type: ignore[return]
        """
        Ensure any custom attributes from other are present on self.
        """
        set_defaults(vars(self), **vars(other))

    def next(self) -> Self:
        cmd = self.__class__.from_datetime(self._next_time())
        cmd.delay = self.delay
        cmd.target = self.target
        reflected: Self = cmd._reflect(self)
        return reflected

    def __setattr__(self, key: str, value: Any) -> None:
        if key == 'delay' and not value > datetime.timedelta():
            raise ValueError("A PeriodicCommand must have a positive, non-zero delay.")
        super().__setattr__(key, value)


class PeriodicCommandFixedDelay(PeriodicCommand):
    """
    Like a periodic command, but don't calculate the delay based on
    the current time. Instead use a fixed delay following the initial
    run.
    """

    @classmethod
    def at_time(  # type: ignore[override] # jaraco/tempora#39
        cls,
        at: datetime.datetime | float,
        delay: datetime.timedelta | numbers.Number,
        target: Any,
    ) -> Self:
        """
        >>> cmd = PeriodicCommandFixedDelay.at_time(0, 30, None)
        >>> cmd.delay.total_seconds()
        30.0
        """
        at = cls._from_timestamp(at)
        cmd = cls.from_datetime(at)
        if isinstance(delay, numbers.Number):
            delay = datetime.timedelta(seconds=delay)  # type: ignore[arg-type] # python/mypy#3186#issuecomment-1571512649
        cmd.delay = delay
        cmd.target = target
        return cmd

    @classmethod
    def daily_at(cls, at: datetime.time, target: Any) -> Self:
        """
        Schedule a command to run at a specific time each day.

        >>> from tempora import utc
        >>> noon = utc.time(12, 0)
        >>> cmd = PeriodicCommandFixedDelay.daily_at(noon, None)
        >>> cmd.delay.total_seconds()
        86400.0
        """
        daily = datetime.timedelta(days=1)
        # convert when to the next datetime matching this time
        when = datetime.datetime.combine(datetime.date.today(), at)
        when -= daily
        while when < now():
            when += daily
        return cls.at_time(when, daily, target)


class Scheduler:
    """
    A rudimentary abstract scheduler accepting DelayedCommands
    and dispatching them on schedule.
    """

    def __init__(self) -> None:
        self.queue: list[DelayedCommand] = []

    def add(self, command: DelayedCommand) -> None:
        bisect.insort(self.queue, command)

    def run_pending(self) -> None:
        while self.queue:
            command = self.queue[0]
            if not command.due():
                break
            self.run(command)
            if isinstance(command, PeriodicCommand):
                self.add(command.next())
            del self.queue[0]

    @abc.abstractmethod
    def run(self, command: DelayedCommand) -> None:
        """
        Run the command
        """


class InvokeScheduler(Scheduler):
    """
    Command targets are functions to be invoked on schedule.
    """

    def run(self, command: DelayedCommand) -> None:
        command.target()


class CallbackScheduler(Scheduler):
    """
    Command targets are passed to a dispatch callable on schedule.
    """

    def __init__(self, dispatch: collections.abc.Callable[..., Any]) -> None:
        super().__init__()
        self.dispatch = dispatch

    def run(self, command: DelayedCommand) -> None:
        self.dispatch(command.target)
