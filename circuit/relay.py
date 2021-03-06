from typing import List

class Relay:
	"""
	The most we can do here is just be able to query the state of the system
	"""
	def __init__(self, power=False, switch=None):
		self._switch_is_on = False
		self._power_source = power
		self._switch_handle = switch

	def switch_on(self):
		self._assert_no_custom_switch()
		self._switch_is_on = True

	def switch_off(self):
		self._assert_no_custom_switch()
		self._switch_is_on = False

	def _assert_no_custom_switch(self):
		if self._switch_handle:
			raise Exception("Can't manually switch if it's already connected to something...")

	def _get_switch_state(self):
		return self._switch_handle() if self._switch_handle else self._switch_is_on

	def _get_power_source_state(self):
		return self._power_source if isinstance(self._power_source, bool) else self._power_source()

	@property
	def output(self):
		# This is just a handle to the output state, making it easier to "connect pieces"
		return lambda: self.output_state

	@property
	def output_state(self):
		return self._get_switch_state() and self._get_power_source_state()

	@staticmethod
	def has_output(relays: List['Relay']) -> bool:
		# This is just an dumb abstraction over what would be "merged" signals, useful in
		# testing relays connected in parallel
		return any([r.output_state for r in relays])
