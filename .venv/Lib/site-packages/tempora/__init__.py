"Objects and routines pertaining to date and time (tempora)"

from __future__ import annotations

__requires__ = [
    'pytest-freezer; extra=="test"',
    'backports.zoneinfo; python_version < "3.9" and extra == "test"',
    'tzdata; platform_system == "Windows" and extra == "test"',
    'types-python-dateutil; extra=="test"',
]

import datetime
import decimal
import functools
import numbers
import re
import time
from collections.abc import Iterable, Iterator, Sequence
from typing import TYPE_CHECKING, Any, cast

import dateutil.parser
import dateutil.tz
from jaraco.collections import RangeMap

if TYPE_CHECKING:
    from typing import TypeAlias

# some useful constants
osc_per_year = 290_091_329_207_984_000
"""
mean vernal equinox year expressed in oscillations of atomic cesium at the
year 2000 (see http://webexhibits.org/calendars/timeline.html for more info).
"""
osc_per_second = 9_192_631_770
seconds_per_second = 1
seconds_per_year = 31_556_940
seconds_per_minute = 60
minutes_per_hour = 60
hours_per_day = 24
seconds_per_hour = seconds_per_minute * minutes_per_hour
seconds_per_day = seconds_per_hour * hours_per_day
days_per_year = seconds_per_year / seconds_per_day
thirty_days = datetime.timedelta(days=30)
# these values provide useful averages
six_months = datetime.timedelta(days=days_per_year / 2)
seconds_per_month = seconds_per_year / 12
hours_per_month = hours_per_day * days_per_year / 12


@functools.lru_cache
def _needs_year_help() -> bool:
    """
    Some versions of Python render %Y with only three characters :(
    https://bugs.python.org/issue39103
    """
    return len(datetime.date(900, 1, 1).strftime('%Y')) != 4


AnyDatetime: TypeAlias = datetime.datetime | datetime.date | datetime.time
StructDatetime: TypeAlias = tuple[int, ...] | time.struct_time


def ensure_datetime(ob: AnyDatetime) -> datetime.datetime:
    """
    Given a datetime or date or time object from the ``datetime``
    module, always return a datetime using default values.
    """
    if isinstance(ob, datetime.datetime):
        return ob
    date = cast(datetime.date, ob)
    time = cast(datetime.time, ob)
    if isinstance(ob, datetime.date):
        time = datetime.time()
    if isinstance(ob, datetime.time):
        date = datetime.date(1900, 1, 1)
    return datetime.datetime.combine(date, time)


def infer_datetime(ob: AnyDatetime | StructDatetime) -> datetime.datetime:
    if isinstance(ob, (time.struct_time, tuple)):
        # '"int" is not assignable to "tzinfo"', but we don't pass that many parameters
        ob = datetime.datetime(*ob[:6])  # type: ignore[arg-type]
    return ensure_datetime(ob)


def strftime(fmt: str, t: AnyDatetime | tuple[int, ...] | time.struct_time) -> str:
    """
    Portable strftime.

    In the stdlib, strftime has `known portability problems
    <https://bugs.python.org/issue13305>`_. This function
    aims to smooth over those issues and provide a
    consistent experience across the major platforms.

    >>> strftime('%Y', datetime.datetime(1890, 1, 1))
    '1890'
    >>> strftime('%Y', datetime.datetime(900, 1, 1))
    '0900'

    Supports time.struct_time, tuples, and datetime.datetime objects.

    >>> strftime('%Y-%m-%d', (1976, 5, 7))
    '1976-05-07'

    Also supports date objects

    >>> strftime('%Y', datetime.date(1976, 5, 7))
    '1976'

    Also supports milliseconds using %s.

    >>> strftime('%s', datetime.time(microsecond=20000))
    '020'

    Also supports microseconds (3 digits) using %µ

    >>> strftime('%µ', datetime.time(microsecond=123456))
    '456'

    Historically, %u was used for microseconds, but now
    it honors the value rendered by stdlib.

    >>> strftime('%u', datetime.date(1976, 5, 7))
    '5'

    Also supports microseconds (6 digits) using %f

    >>> strftime('%f', datetime.time(microsecond=23456))
    '023456'

    Even supports time values on date objects (discouraged):

    >>> strftime('%f', datetime.date(1976, 1, 1))
    '000000'
    >>> strftime('%µ', datetime.date(1976, 1, 1))
    '000'
    >>> strftime('%s', datetime.date(1976, 1, 1))
    '000'

    And vice-versa:

    >>> strftime('%Y', datetime.time())
    '1900'
    """
    t = infer_datetime(t)
    subs = (
        ('%s', f'{t.microsecond // 1000:03d}'),
        ('%µ', f'{t.microsecond % 1000:03d}'),
    ) + (('%Y', f'{t.year:04d}'),) * _needs_year_help()

    def doSub(s: str, sub: tuple[str, str]) -> str:
        return s.replace(*sub)

    def doSubs(s: str) -> str:
        return functools.reduce(doSub, subs, s)

    fmt = '%%'.join(map(doSubs, fmt.split('%%')))
    return t.strftime(fmt)


def datetime_mod(
    dt: datetime.datetime,
    period: datetime.timedelta,
    start: datetime.datetime | None = None,
) -> datetime.datetime:
    """
    Find the time which is the specified date/time truncated to the time delta
    relative to the start date/time.
    By default, the start time is midnight of the same day as the specified
    date/time.

    >>> datetime_mod(datetime.datetime(2004, 1, 2, 3),
    ...     datetime.timedelta(days = 1.5),
    ...     start = datetime.datetime(2004, 1, 1))
    datetime.datetime(2004, 1, 1, 0, 0)
    >>> datetime_mod(datetime.datetime(2004, 1, 2, 13),
    ...     datetime.timedelta(days = 1.5),
    ...     start = datetime.datetime(2004, 1, 1))
    datetime.datetime(2004, 1, 2, 12, 0)
    >>> datetime_mod(datetime.datetime(2004, 1, 2, 13),
    ...     datetime.timedelta(days = 7),
    ...     start = datetime.datetime(2004, 1, 1))
    datetime.datetime(2004, 1, 1, 0, 0)
    >>> datetime_mod(datetime.datetime(2004, 1, 10, 13),
    ...     datetime.timedelta(days = 7),
    ...     start = datetime.datetime(2004, 1, 1))
    datetime.datetime(2004, 1, 8, 0, 0)
    """
    if start is None:
        # use midnight of the same day
        start = datetime.datetime.combine(dt.date(), datetime.time())
    # calculate the difference between the specified time and the start date.
    delta = dt - start

    # now aggregate the delta and the period into microseconds
    # Use microseconds because that's the highest precision of these time
    # pieces.  Also, using microseconds ensures perfect precision (no floating
    # point errors).
    def get_time_delta_microseconds(td: datetime.timedelta) -> int:
        return (td.days * seconds_per_day + td.seconds) * 1000000 + td.microseconds

    delta, period = map(get_time_delta_microseconds, (delta, period))  # type: ignore[assignment]
    offset = datetime.timedelta(microseconds=delta % period)  # type: ignore[arg-type]
    # the result is the original specified time minus the offset
    result = dt - offset
    return result


def datetime_round(
    dt: datetime.datetime,
    period: datetime.timedelta,
    start: datetime.datetime | None = None,
) -> datetime.datetime:
    """
    Find the nearest even period for the specified date/time.

    >>> datetime_round(datetime.datetime(2004, 11, 13, 8, 11, 13),
    ...     datetime.timedelta(hours = 1))
    datetime.datetime(2004, 11, 13, 8, 0)
    >>> datetime_round(datetime.datetime(2004, 11, 13, 8, 31, 13),
    ...     datetime.timedelta(hours = 1))
    datetime.datetime(2004, 11, 13, 9, 0)
    >>> datetime_round(datetime.datetime(2004, 11, 13, 8, 30),
    ...     datetime.timedelta(hours = 1))
    datetime.datetime(2004, 11, 13, 9, 0)
    """
    result = datetime_mod(dt, period, start)
    if abs(dt - result) >= period // 2:
        result += period
    return result


def get_nearest_year_for_day(day: int) -> int:
    """
    Returns the nearest year to now inferred from a Julian date.

    >>> freezer = getfixture('freezer')
    >>> freezer.move_to('2019-05-20')
    >>> get_nearest_year_for_day(20)
    2019
    >>> get_nearest_year_for_day(340)
    2018
    >>> freezer.move_to('2019-12-15')
    >>> get_nearest_year_for_day(20)
    2020
    """
    now = time.gmtime()
    result = now.tm_year
    # if the day is far greater than today, it must be from last year
    if day - now.tm_yday > 365 // 2:
        result -= 1
    # if the day is far less than today, it must be for next year.
    if now.tm_yday - day > 365 // 2:
        result += 1
    return result


def gregorian_date(year: int, julian_day: int) -> datetime.date:
    """
    Gregorian Date is defined as a year and a julian day (1-based
    index into the days of the year).

    >>> gregorian_date(2007, 15)
    datetime.date(2007, 1, 15)
    """
    result = datetime.date(year, 1, 1)
    result += datetime.timedelta(days=julian_day - 1)
    return result


@functools.singledispatch
def get_period_seconds(
    period: str | numbers.Number | datetime.timedelta,
) -> numbers.Number:
    """
    return the number of seconds in the specified period

    >>> get_period_seconds('day')
    86400
    >>> get_period_seconds(86400)
    86400
    >>> get_period_seconds(datetime.timedelta(hours=24))
    86400
    >>> get_period_seconds('day + os.system("rm -Rf *")')
    Traceback (most recent call last):
    ...
    ValueError: period not in (second, minute, hour, day, month, year)
    """
    raise TypeError('period must be a string or integer')


@get_period_seconds.register
def _(period: str) -> numbers.Number:
    try:
        name = 'seconds_per_' + period.lower()
        return cast(numbers.Number, globals()[name])
    except KeyError:
        raise ValueError("period not in (second, minute, hour, day, month, year)")


@get_period_seconds.register
def _(period: numbers.Number) -> numbers.Number:
    return period


@get_period_seconds.register
def _(period: datetime.timedelta) -> numbers.Number:
    return period.days * get_period_seconds('day') + period.seconds  # type: ignore[operator]


def get_date_format_string(period: str | numbers.Number | datetime.timedelta) -> str:
    """
    For a given period (e.g. 'month', 'day', or some numeric interval
    such as 3600 (in secs)), return the format string that can be
    used with strftime to format that time to specify the times
    across that interval, but no more detailed.
    For example,

    >>> get_date_format_string('month')
    '%Y-%m'
    >>> get_date_format_string(3600)
    '%Y-%m-%d %H'
    >>> get_date_format_string('hour')
    '%Y-%m-%d %H'
    >>> get_date_format_string(None)
    Traceback (most recent call last):
        ...
    TypeError: period must be a string or integer
    >>> get_date_format_string('garbage')
    Traceback (most recent call last):
        ...
    ValueError: period not in (second, minute, hour, day, month, year)
    """
    # handle the special case of 'month' which doesn't have
    #  a static interval in seconds
    if isinstance(period, str) and period.lower() == 'month':
        return '%Y-%m'
    file_period_secs = get_period_seconds(period)
    format_pieces: Sequence[str] = ('%Y', '-%m-%d', ' %H', '-%M', '-%S')
    seconds_per_second = 1
    intervals = (
        seconds_per_year,
        seconds_per_day,
        seconds_per_hour,
        seconds_per_minute,
        seconds_per_second,
    )
    mods = list(map(lambda interval: file_period_secs % interval, intervals))  # type: ignore[operator]
    format_pieces = format_pieces[: mods.index(0) + 1]
    return ''.join(format_pieces)


def calculate_prorated_values() -> None:
    """
    >>> monkeypatch = getfixture('monkeypatch')
    >>> import builtins
    >>> monkeypatch.setattr(builtins, 'input', lambda prompt: '3/hour')
    >>> calculate_prorated_values()
    per minute: 0.05
    per hour: 3.0
    per day: 72.0
    per month: 2191.454166666667
    per year: 26297.45
    """
    rate = input("Enter the rate (3/hour, 50/month)> ")
    for period, value in _prorated_values(rate):
        print(f"per {period}: {value}")


def _prorated_values(rate: str) -> Iterator[tuple[str, float]]:
    """
    Given a rate (a string in units per unit time), and return that same
    rate for various time periods.

    >>> for period, value in _prorated_values('20/hour'):
    ...     print('{period}: {value:0.3f}'.format(**locals()))
    minute: 0.333
    hour: 20.000
    day: 480.000
    month: 14609.694
    year: 175316.333

    """
    match = re.match(r'(?P<value>[\d.]+)/(?P<period>\w+)$', rate)
    res = cast(re.Match[str], match).groupdict()
    value = float(res['value'])
    value_per_second = value / get_period_seconds(res['period'])  # type: ignore[operator]
    for period in ('minute', 'hour', 'day', 'month', 'year'):
        period_value = value_per_second * get_period_seconds(period)  # type: ignore[operator]
        yield period, period_value


def parse_timedelta(str: str) -> datetime.timedelta:
    """
    Take a string representing a span of time and parse it to a time delta.
    Accepts any string of comma-separated numbers each with a unit indicator.

    >>> parse_timedelta('1 day')
    datetime.timedelta(days=1)

    >>> parse_timedelta('1 day, 30 seconds')
    datetime.timedelta(days=1, seconds=30)

    >>> parse_timedelta('47.32 days, 20 minutes, 15.4 milliseconds')
    datetime.timedelta(days=47, seconds=28848, microseconds=15400)

    Supports weeks, months, years

    >>> parse_timedelta('1 week')
    datetime.timedelta(days=7)

    >>> parse_timedelta('1 year, 1 month')
    datetime.timedelta(days=395, seconds=58685)

    Note that months and years strict intervals, not aligned
    to a calendar:

    >>> date = datetime.datetime.fromisoformat('2000-01-01')
    >>> later = date + parse_timedelta('1 year')
    >>> diff = later.replace(year=date.year) - date
    >>> diff.seconds
    20940

    >>> parse_timedelta('foo')
    Traceback (most recent call last):
    ...
    ValueError: Unexpected 'foo'

    >>> parse_timedelta('14 seconds foo')
    Traceback (most recent call last):
    ...
    ValueError: Unexpected 'foo'

    Supports abbreviations:

    >>> parse_timedelta('1s')
    datetime.timedelta(seconds=1)

    >>> parse_timedelta('1sec')
    datetime.timedelta(seconds=1)

    >>> parse_timedelta('5min1sec')
    datetime.timedelta(seconds=301)

    >>> parse_timedelta('1 ms')
    datetime.timedelta(microseconds=1000)

    >>> parse_timedelta('1 µs')
    datetime.timedelta(microseconds=1)

    >>> parse_timedelta('1 us')
    datetime.timedelta(microseconds=1)

    And supports the common colon-separated duration:

    >>> parse_timedelta('14:00:35.362')
    datetime.timedelta(seconds=50435, microseconds=362000)

    TODO: Should this be 14 hours or 14 minutes?

    >>> parse_timedelta('14:00')
    datetime.timedelta(seconds=50400)

    >>> parse_timedelta('14:00 minutes')
    Traceback (most recent call last):
    ...
    ValueError: Cannot specify units with composite delta

    Because a timedelta only has microsecond resolution, nanoseconds
    (and other sub-microsecond values) get rounded to the nearest
    microsecond. Use :func:`parse_nanoseconds` to retain that precision.

    >>> parse_timedelta('600 ns')
    datetime.timedelta(microseconds=1)

    >>> parse_timedelta('.002 µs, 499 ns')
    datetime.timedelta(microseconds=1)

    >>> parse_timedelta('1.6 µs')
    datetime.timedelta(microseconds=2)

    Expect ValueError for other invalid inputs.

    >>> parse_timedelta('13 feet')
    Traceback (most recent call last):
    ...
    ValueError: Invalid unit feets
    """
    return _parse_timedelta_nanos(str).resolve()


def parse_nanoseconds(str: str) -> decimal.Decimal:
    """
    Parse a string representing a span of time, returning the total
    number of nanoseconds as a :class:`decimal.Decimal`.

    Unlike :func:`parse_timedelta`, which is limited to the microsecond
    resolution of :class:`datetime.timedelta`, this retains
    sub-microsecond precision.

    >>> parse_nanoseconds('600 ns')
    Decimal('600.0')

    >>> parse_nanoseconds('34.2 nsec')
    Decimal('34.2')

    >>> parse_nanoseconds('1.6 µs')
    Decimal('1600.0')

    >>> parse_nanoseconds('.002 µs, 499 ns')
    Decimal('501.000')

    >>> parse_nanoseconds('1 ms')
    Decimal('1000000.0')

    Coarser units are supported too.

    >>> parse_nanoseconds('1 day')
    Decimal('86400000000000')
    """
    return _parse_timedelta_nanos(str).total_nanoseconds


@functools.total_ordering
class Duration:
    """
    A span of time with nanosecond resolution.

    Where :class:`datetime.timedelta` bottoms out at microsecond
    resolution, a Duration retains sub-microsecond precision, making it
    suitable for expressing and comparing very short intervals such as
    the output of :mod:`timeit`.

    Construct from a number of nanoseconds or from keyword units:

    >>> Duration(34.2)
    Duration(Decimal('34.2'))
    >>> Duration(microseconds=1.6)
    Duration(Decimal('1600.0'))
    >>> Duration(seconds=1, nanoseconds=5)
    Duration(Decimal('1000000005'))

    Or parse a textual duration (see :func:`parse_nanoseconds`):

    >>> Duration.parse('34.2 nsec')
    Duration(Decimal('34.2'))

    Rendered with the most natural unit:

    >>> print(Duration.parse('34.2 nsec'))
    34.2 nsec
    >>> print(Duration(microseconds=1.6))
    1.6 µsec
    >>> print(Duration(milliseconds=12.3))
    12.3 msec
    >>> print(Duration(seconds=2))
    2 sec
    >>> print(Duration(0))
    0 nsec

    Durations add and subtract to yield Durations, and divide by one
    another to yield a dimensionless ratio:

    >>> Duration.parse('38.1 nsec') - Duration.parse('34.2 nsec')
    Duration(Decimal('3.9'))
    >>> Duration.parse('38.1 nsec') / Duration.parse('34.2 nsec')
    Decimal('1.11...')

    Multiply or divide by a scalar to scale:

    >>> print(Duration(microseconds=1) / 4)
    250 nsec
    >>> print(Duration(nanoseconds=250) * 4)
    1 µsec

    They compare and sort by magnitude, and are falsey when zero:

    >>> Duration(5) < Duration(microseconds=1)
    True
    >>> bool(Duration(0))
    False

    Interoperate with :class:`datetime.timedelta` (rounding to its
    microsecond resolution):

    >>> Duration.from_timedelta(datetime.timedelta(seconds=1))
    Duration(Decimal('1000000000'))
    >>> Duration(microseconds=1.6).timedelta()
    datetime.timedelta(microseconds=2)
    """

    _ns_per = dict(
        nanoseconds=1,
        microseconds=10**3,
        milliseconds=10**6,
        seconds=10**9,
    )

    _scale = RangeMap.left({
        decimal.Decimal(0): (decimal.Decimal(1), 'nsec'),
        decimal.Decimal(10**3): (decimal.Decimal(10**3), 'µsec'),
        decimal.Decimal(10**6): (decimal.Decimal(10**6), 'msec'),
        decimal.Decimal(10**9): (decimal.Decimal(10**9), 'sec'),
    })

    def __init__(self, nanoseconds: float | decimal.Decimal = 0, **units: float):
        total = decimal.Decimal(str(nanoseconds))
        for unit, value in units.items():
            try:
                factor = self._ns_per[unit]
            except KeyError:
                raise ValueError(f"Invalid unit {unit!r}")
            total += decimal.Decimal(str(value)) * factor
        self.nanoseconds = total

    @classmethod
    def parse(cls, spec: str) -> Duration:
        return cls(parse_nanoseconds(spec))

    @classmethod
    def from_timedelta(cls, delta: datetime.timedelta) -> Duration:
        return cls(microseconds=delta // datetime.timedelta(microseconds=1))

    def timedelta(self) -> datetime.timedelta:
        micros = round(self.nanoseconds / self._ns_per['microseconds'])
        return datetime.timedelta(microseconds=micros)

    def total_seconds(self) -> decimal.Decimal:
        return self.nanoseconds / self._ns_per['seconds']

    def __str__(self) -> str:
        factor, unit = self._scale[abs(self.nanoseconds)]
        return f'{float(self.nanoseconds / factor):.3g} {unit}'

    def __repr__(self) -> str:
        return f'{type(self).__name__}({self.nanoseconds!r})'

    def __add__(self, other: Duration) -> Duration:
        if not isinstance(other, Duration):
            return NotImplemented
        return Duration(self.nanoseconds + other.nanoseconds)

    def __sub__(self, other: Duration) -> Duration:
        if not isinstance(other, Duration):
            return NotImplemented
        return Duration(self.nanoseconds - other.nanoseconds)

    def __mul__(self, other: float) -> Duration:
        if not isinstance(other, numbers.Real):
            return NotImplemented
        return Duration(self.nanoseconds * decimal.Decimal(str(other)))

    __rmul__ = __mul__

    def __truediv__(self, other: Duration | float) -> Duration | decimal.Decimal:
        if isinstance(other, Duration):
            return self.nanoseconds / other.nanoseconds
        if isinstance(other, numbers.Real):
            return Duration(self.nanoseconds / decimal.Decimal(str(other)))
        return NotImplemented

    def __neg__(self) -> Duration:
        return Duration(-self.nanoseconds)

    def __abs__(self) -> Duration:
        return Duration(abs(self.nanoseconds))

    def __bool__(self) -> bool:
        return bool(self.nanoseconds)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Duration):
            return NotImplemented
        return self.nanoseconds == other.nanoseconds

    def __lt__(self, other: Duration) -> bool:
        if not isinstance(other, Duration):
            return NotImplemented
        return self.nanoseconds < other.nanoseconds

    def __hash__(self) -> int:
        return hash(self.nanoseconds)


def _parse_timedelta_nanos(str: str) -> _Saved_NS:
    parts = re.finditer(r'(?P<value>[\d.:]+)\s?(?P<unit>[^\W\d_]+)?', str)
    chk_parts = _check_unmatched(parts, str)
    deltas = map(_parse_timedelta_part, chk_parts)
    return sum(deltas, _Saved_NS())


def _check_unmatched(
    matches: Iterable[re.Match[str]], text: str
) -> Iterator[re.Match[str]]:
    """
    Ensure no words appear in unmatched text.
    """

    def check_unmatched(unmatched: str) -> None:
        found = re.search(r'\w+', unmatched)
        if found:
            raise ValueError(f"Unexpected {found.group(0)!r}")

    pos = 0
    for match in matches:
        check_unmatched(text[pos : match.start()])
        yield match
        pos = match.end()
    check_unmatched(text[pos:])


_unit_lookup = {
    'µs': 'microsecond',
    'µsec': 'microsecond',
    'us': 'microsecond',
    'usec': 'microsecond',
    'micros': 'microsecond',
    'ms': 'millisecond',
    'msec': 'millisecond',
    'millis': 'millisecond',
    's': 'second',
    'sec': 'second',
    'h': 'hour',
    'hr': 'hour',
    'm': 'minute',
    'min': 'minute',
    'w': 'week',
    'wk': 'week',
    'd': 'day',
    'ns': 'nanosecond',
    'nsec': 'nanosecond',
    'nanos': 'nanosecond',
}


def _resolve_unit(raw_match: str | None) -> str:
    if raw_match is None:
        return 'second'
    text = raw_match.lower()
    return _unit_lookup.get(text, text)


def _parse_timedelta_composite(raw_value: str, unit: str) -> _Saved_NS:
    if unit != 'seconds':
        raise ValueError("Cannot specify units with composite delta")
    values = raw_value.split(':')
    units = 'hours', 'minutes', 'seconds'
    composed = ' '.join(f'{value} {unit}' for value, unit in zip(values, units))
    return _parse_timedelta_nanos(composed)


def _parse_timedelta_part(match: re.Match[str]) -> _Saved_NS:
    unit = _resolve_unit(match.group('unit'))
    if not unit.endswith('s'):
        unit += 's'
    raw_value = match.group('value')
    if ':' in raw_value:
        return _parse_timedelta_composite(raw_value, unit)
    value = float(raw_value)
    if unit == 'months':
        unit = 'years'
        value = value / 12
    if unit == 'years':
        unit = 'days'
        value = value * days_per_year
    return _Saved_NS.derive(unit, value)


class _Saved_NS:
    """
    Bundle a timedelta with a sub-microsecond nanoseconds remainder.

    ``td`` carries whole-microsecond resolution and ``nanoseconds`` the
    exact sub-microsecond remainder, so that ``total_nanoseconds``
    reconstructs the full precision of the parsed value.

    >>> _Saved_NS.derive('microseconds', .001)
    _Saved_NS(td=datetime.timedelta(0), nanoseconds=Decimal('1.000'))
    """

    td = datetime.timedelta()
    nanoseconds: decimal.Decimal = decimal.Decimal(0)
    multiplier = dict(
        seconds=1000000000,
        milliseconds=1000000,
        microseconds=1000,
        nanoseconds=1,
    )

    def __init__(self, **kwargs: Any) -> None:
        vars(self).update(kwargs)

    @classmethod
    def derive(cls, unit: str, value: float) -> _Saved_NS:
        try:
            factor = cls.multiplier[unit]
        except KeyError:
            try:
                return _Saved_NS(td=datetime.timedelta(**{unit: value}))
            except TypeError:
                raise ValueError(f"Invalid unit {unit}")
        # Track the value exactly in nanoseconds, then split into a
        # whole-microsecond timedelta and the sub-microsecond remainder.
        total_ns = decimal.Decimal(str(value)) * factor
        whole_us, rem_ns = divmod(total_ns, 1000)
        return _Saved_NS(
            td=datetime.timedelta(microseconds=int(whole_us)), nanoseconds=rem_ns
        )

    def __add__(self, other: _Saved_NS) -> _Saved_NS:
        return _Saved_NS(
            td=self.td + other.td, nanoseconds=self.nanoseconds + other.nanoseconds
        )

    @property
    def total_nanoseconds(self) -> decimal.Decimal:
        """
        The full parsed value expressed in nanoseconds, retaining
        sub-microsecond resolution.
        """
        whole_us = self.td // datetime.timedelta(microseconds=1)
        return whole_us * 1000 + self.nanoseconds

    def resolve(self) -> datetime.timedelta:
        """
        Resolve to a timedelta, rounding to the nearest microsecond
        (discarding any nanosecond resolution).
        """
        micros = round(self.total_nanoseconds / 1000)
        return datetime.timedelta(microseconds=micros)

    def __repr__(self) -> str:
        return f'_Saved_NS(td={self.td!r}, nanoseconds={self.nanoseconds!r})'


def date_range(
    start: datetime.datetime | None = None,
    stop: datetime.datetime | None = None,
    step: datetime.timedelta | None = None,
) -> Iterator[datetime.datetime]:
    """
    Much like the built-in function range, but works with dates

    >>> range_items = date_range(
    ...     datetime.datetime(2005,12,21),
    ...     datetime.datetime(2005,12,25),
    ... )
    >>> my_range = tuple(range_items)
    >>> datetime.datetime(2005,12,21) in my_range
    True
    >>> datetime.datetime(2005,12,22) in my_range
    True
    >>> datetime.datetime(2005,12,25) in my_range
    False
    >>> from_now = date_range(stop=datetime.datetime(2099, 12, 31))
    >>> next(from_now)
    datetime.datetime(...)
    """
    if step is None:
        step = datetime.timedelta(days=1)
    if start is None:
        start = datetime.datetime.now()
    while start < stop:  # type: ignore[operator]  # stop may be None if not provided
        yield start
        start += step


tzinfos = dict(
    AEST=dateutil.tz.gettz("Australia/Sydney"),
    AEDT=dateutil.tz.gettz("Australia/Sydney"),
    ACST=dateutil.tz.gettz("Australia/Darwin"),
    ACDT=dateutil.tz.gettz("Australia/Adelaide"),
    AWST=dateutil.tz.gettz("Australia/Perth"),
    EST=dateutil.tz.gettz("America/New_York"),
    EDT=dateutil.tz.gettz("America/New_York"),
    CST=dateutil.tz.gettz("America/Chicago"),
    CDT=dateutil.tz.gettz("America/Chicago"),
    MST=dateutil.tz.gettz("America/Denver"),
    MDT=dateutil.tz.gettz("America/Denver"),
    PST=dateutil.tz.gettz("America/Los_Angeles"),
    PDT=dateutil.tz.gettz("America/Los_Angeles"),
    GMT=dateutil.tz.gettz("Etc/GMT"),
    UTC=dateutil.tz.gettz("UTC"),
    CET=dateutil.tz.gettz("Europe/Berlin"),
    CEST=dateutil.tz.gettz("Europe/Berlin"),
    IST=dateutil.tz.gettz("Asia/Kolkata"),
    BST=dateutil.tz.gettz("Europe/London"),
    MSK=dateutil.tz.gettz("Europe/Moscow"),
    EET=dateutil.tz.gettz("Europe/Helsinki"),
    EEST=dateutil.tz.gettz("Europe/Helsinki"),
    # Add more mappings as needed
)


def parse(*args: Any, **kwargs: Any) -> datetime.datetime:
    """
    Parse the input using dateutil.parser.parse with friendly tz support.

    >>> parse('2024-07-26 12:59:00 EDT')
    datetime.datetime(...America/New_York...)
    """
    return dateutil.parser.parse(*args, tzinfos=tzinfos, **kwargs)  # type: ignore[no-any-return]
