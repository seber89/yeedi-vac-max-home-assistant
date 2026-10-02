"""Optional position-only polling; no map, status, history or persistent data."""
import asyncio
import time

from .client import InvalidAuth, VerificationRequired, RateLimited, CommandTimeout

INTERVAL = 5
TIMEOUT = 5
ERROR_BACKOFF = 15
RATE_BACKOFF = 300
RESULTS = frozenset(('never', 'success', 'missing_position', 'timeout',
                     'cloud_error', 'rate_limited', 'auth_error', 'stopped'))


def bucket(count):
    if type(count) is not int or count < 0:
        return '0'
    return '0' if count == 0 else '1' if count == 1 else '2-8' if count <= 8 else '9-32' if count <= 32 else '>32'


class FastPosition:
    """One cancellable task per robot; all device reads share the command lock."""

    def __init__(self, coordinator, robot):
        self.coordinator = coordinator
        self.robot = robot
        self.task = None
        self.wanted = False
        self.closed = False
        self.auth_blocked = False
        self.next_read = 0.0  # Scheduling only, not a position timestamp/history.
        self.read_started = float('-inf')  # Single cadence guard shared with normal getPos.
        self.last_result = 'never'
        self.successes = self.failures = 0
        self.rate_limited = False
        self.restart_requested = False

    def observe(self, snapshot):
        wanted = bool(snapshot.get('online')) and snapshot.get('activity') in {'cleaning', 'returning'}
        if self.closed:
            return
        was_wanted = self.wanted
        self.wanted = wanted
        if not wanted:
            self.restart_requested = False
            self.auth_blocked = self.rate_limited = False
            if self.task is not None:
                self.last_result = 'stopped'
                self.task.cancel()
            return
        if not was_wanted:
            self.next_read = time.monotonic() + INTERVAL
            self.restart_requested = self.task is not None and self.task.cancelling() > 0
        self._start()

    def _start(self):
        if not self.closed and self.wanted and not self.auth_blocked and self.task is None:
            self.task = self.coordinator.config_entry.async_create_background_task(
                self.coordinator.hass, self._run(), 'Yeedi position-only poll', eager_start=False)
            self.task.add_done_callback(self._finished)

    def _finished(self, task):
        if self.task is task:
            self.task = None
        # Cancellation on a rapid stop/start finishes before a replacement starts.
        # HA shutdown cancellation must not recreate a task.
        restart = self.restart_requested
        self.restart_requested = False
        if restart and not self.coordinator.hass.is_stopping:
            self._start()

    def note_normal_read(self):
        self.read_started = time.monotonic()
        self.next_read = max(self.next_read, time.monotonic() + INTERVAL)

    def normal_read_due(self):
        return not self.wanted or time.monotonic() >= self.read_started + INTERVAL

    async def _run(self):
        try:
            while self.wanted and not self.closed and not self.auth_blocked:
                await asyncio.sleep(max(0, self.next_read - time.monotonic()))
                if not self.wanted or self.closed:
                    return
                await self._cycle()
        except asyncio.CancelledError:
            raise
        except Exception:
            # Never let private third-party exception text reach HA task logging.
            self.last_result = 'cloud_error'
            self.failures = min(33, self.failures + 1)
            self.next_read = time.monotonic() + ERROR_BACKOFF

    async def _cycle(self):
        command = self.coordinator.commands[self.robot.did]
        now = time.monotonic()
        if not self.wanted or self.closed or self.auth_blocked or now < self.next_read:
            return
        if command.lock.locked() or command.pending:
            self.next_read = now + INTERVAL
            return  # No lock waiters or read queue.
        self.next_read = now + INTERVAL
        try:
            # No await between availability check and uncontended acquisition.
            async with command.lock:
                self.read_started = time.monotonic()
                async with asyncio.timeout(TIMEOUT):
                    robot_pos, dock_pos = await self.coordinator.client.positions(self.robot, retry=False)
                if not self.wanted or self.closed:
                    return
                state = self.coordinator.spatial[self.robot.did]
                state.robot_position, state.dock_position = robot_pos, dock_pos
                self.last_result = 'success' if robot_pos is not None else 'missing_position'
                self.successes = min(33, self.successes + 1)
                self.rate_limited = False
                self.coordinator.async_update_listeners()
        except (InvalidAuth, VerificationRequired):
            self.auth_blocked = True
            self.last_result = 'auth_error'
            self.failures = min(33, self.failures + 1)
        except RateLimited:
            self.rate_limited = True
            self._failure('rate_limited', RATE_BACKOFF)
        except (TimeoutError, CommandTimeout):
            self._failure('timeout', ERROR_BACKOFF)
        except Exception:
            self._failure('cloud_error', ERROR_BACKOFF)

    def _failure(self, result, delay):
        self.last_result = result
        self.failures = min(33, self.failures + 1)
        self.next_read = time.monotonic() + delay

    async def shutdown(self):
        self.closed = True
        self.wanted = False
        task = self.task
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self.task = None

    def diagnostics(self):
        return {
            'fast_position_poll_active': bool(self.task is not None and not self.task.done() and self.wanted and not self.auth_blocked),
            'fast_position_last_result': self.last_result if type(self.last_result) is str and self.last_result in RESULTS else 'cloud_error',
            'fast_position_success_bucket': bucket(self.successes),
            'fast_position_failure_bucket': bucket(self.failures),
            'fast_position_rate_limited': self.rate_limited is True,
        }
