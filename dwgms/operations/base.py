# Confidential & Proprietary Information: D-Wave Systems Inc.
from __future__ import annotations

import warnings
from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Hashable, Optional, Sequence, Type, Union

from dwgms.circuit import CircuitContext, CircuitError
from dwgms.mixedproperty import abstractmixedproperty, mixedproperty
from dwgms.tools.unitary import build_controlled_unitary

if TYPE_CHECKING:
    from numpy.typing import NDArray

# IDEA: use a functional approach, instead of an object oriented approach, for
# utility functions such as 'broadcast', 'decompose' and 'get_matrix'.


class ABCLockedAttr(ABCMeta):
    """Metaclass to lock certain class attributes from being overwritten
    with instance attributes. Used by the ``Operation`` abstract class."""

    locked_attributes = [
        "matrix",
    ]

    def __setattr__(self, attr, value) -> None:
        if attr in self.locked_attributes:
            raise ValueError(f"Cannot set class attribute '{attr}' to '{value}'.")

        super(ABCLockedAttr, self).__setattr__(attr, value)


class Operation(metaclass=ABCLockedAttr):
    """Class representing a classical or quantum operation.

    Args:
        qubits: Qubits on which the operation should be applied. Only
            required when applying an operation within a circuit context.
    """

    def __init__(self, qubits: Optional[Union[Hashable, Sequence[Hashable]]] = None) -> None:
        active_context = CircuitContext.active_context

        if qubits is not None:
            qubits = self._check_qubits(qubits)

        elif active_context is not None:
            raise TypeError("Qubits required when applying gate within context.")

        # must be set before appending operation to circuit
        self._qubits = qubits

        if active_context is not None and active_context.frozen is False:
            active_context.circuit.append(self)

    @abstractmixedproperty
    def _num_qubits(cls):
        """Abstract mixedproperty asserting the existence of a ``_num_qubits`` attribute."""
        pass

    @classmethod
    def _check_qubits(cls, qubits: Sequence[Hashable]) -> Sequence[Hashable]:
        """Asserts size and type of the qubit(s) and returns the correct type.

        Args:
            qubits: Qubits to check.

        Returns:
            tuple: Sequence of qubits as a tuple.
        """
        # TODO: update to check for single qubit instead of str
        if isinstance(qubits, str) or not isinstance(qubits, Sequence):
            qubits = [qubits]

        if len(qubits) != cls.num_qubits:
            raise ValueError(
                f"Operation '{cls.label}' requires " f"{cls.num_qubits} qubits, got {len(qubits)}."
            )

        # cast to tuple for convention
        return tuple(qubits)

    def __call__(self, qubits: Optional[Sequence[Hashable]] = None):
        """Apply (or reapply) the operation within a context.

        Args:
            qubits: Qubits on which the operation should be applied. Only
                required if not already declared in operation.
        """
        qubits = qubits or self.qubits
        self.__class__(qubits)

    def __eq__(self, __o: object) -> bool:
        """Returns whether two operations are considered equal."""
        name_eq = __o.__class__.__name__ == self.__class__.__name__
        return name_eq and __o.qubits == self.qubits

    def __str__(self) -> str:
        """Returns the operation representation."""
        return repr(self)

    def __repr__(self) -> str:
        """Returns the representation of the Operation object."""
        return f"<{self.__class__.__base__.__name__}: {self.label}, qubits={self.qubits}>"

    @mixedproperty
    def label(cls, self) -> str:
        """Qubit operation label."""
        if self and hasattr(self, "parameters"):
            params = f"({self.parameters})"
            return cls.__name__ + params
        return cls.__name__

    @mixedproperty
    def decomposition(cls) -> Sequence[Hashable]:
        """Decomposition of operation as list of operation labels."""
        if not getattr(cls, "_decomposition", None):
            raise NotImplementedError(
                "Decomposition not implemented for the " f"'{cls.label}' operation."
            )
        return cls._decomposition

    @mixedproperty
    def num_qubits(cls) -> int:
        """Number of qubits that the operation supports."""
        if isinstance(cls._num_qubits, int):
            return cls._num_qubits

        raise AttributeError(f"Operations {cls.label} missing class attributes '_num_qubits'.")

    @property
    def qubits(self) -> Sequence[Hashable]:
        """Qubits that the operation is applied to."""
        return self._qubits

    @qubits.setter
    def qubits(self, qubits: Sequence[Hashable]) -> None:
        """Set the qubits that the operation should be applied to."""
        if self.qubits is not None:
            warnings.warn(
                f"Changing qubits on which '{self}' is applied from {self._qubits} to {qubits}"
            )
        self._qubits = self._check_qubits(qubits)

    @classmethod
    def broadcast(
        cls,
        qubits: Sequence[Hashable],
        parameters: Sequence[complex] = None,
        method: str = "layered",
    ) -> None:
        """Broadcasts an operation over one or more qubits.

        Args:
            qubits: Qubits to broadcast the operation over.
            parameters: Operation parameters, if required by operation.
            method: Which method to use for broadcasting (defaults to
                ``"layered"``). Currently supports the following methods:

                - layered: Applies the operation starting at the first qubit,
                    incrementing by a single qubit per round; e.g., a 2-qubit gate
                    applied to 3 qubits would apply it first to (0, 1), then (1, 2).
                - parallel: Applies the operation starting at the first qubit,
                    incrementing by the number of supported qubits for that gate;
                    e.g., a 2-qubit gate applied to 5 qubits would apply it first
                    to (0, 1), then (2, 3) and not apply anything to qubit 4.
        Raises:
            ValueError: If an unsupported method is requested.
        """
        if CircuitContext.active_context is None:
            raise CircuitError("Can only broadcast gates within a circuit context.")

        # add parameters to operation call if required
        if issubclass(cls, ParametricOperation):
            if not parameters:
                raise ValueError("Parmeters required for broadcasting parametric operation.")
            append = lambda start, end: cls(parameters, qubits[start:end])
        elif issubclass(cls, ControlledOperation):
            num_control = getattr(cls, "_num_control", 0)
            append = lambda start, end: cls(
                qubits[start : start + num_control], qubits[start + num_control : end]
            )
        elif issubclass(cls, Operation):
            append = lambda start, end: cls(qubits[start:end])
        else:
            raise ValueError("Must be a class of type 'Operation'.")

        if method == "layered":
            for i, _ in enumerate(qubits[: -cls.num_qubits + 1 or None]):
                append(i, i + cls.num_qubits)
        elif method == "parallel":
            for i, _ in enumerate(qubits[:: cls.num_qubits]):
                start, end = cls.num_qubits * i, cls.num_qubits * (i + 1)
                if end <= len(qubits):
                    append(start, end)
        else:
            raise ValueError(f"'{method}' style not supported.")

    @abstractmethod
    def to_qasm(self):
        """Converts the operation into an OpenQASM string.

        Returns:
            str: OpenQASM string representation of the operation.
        """
        pass

    @abstractmixedproperty
    def matrix(cls) -> NDArray:
        """Returns the matrix representation of the operation.

        Returns:
            NDArray: Matrix representation of the operation.
        """
        pass


class ParametricOperation(Operation):
    """Class for creating parametric operations.

    Args:
        qubits: Qubits on which the operation should be applied. Only
            required when applying an operation within a circuit context.
        parameters: Parameters for the operation. Required when constructing the
            matrix representation of the operation.
    """

    def __init__(
        self,
        parameters: Sequence[complex],
        qubits: Optional[Union[str, Sequence[str]]] = None,
    ):
        self._parameters = self._check_parameters(parameters)
        super(ParametricOperation, self).__init__(qubits)

    def __eq__(self, __o: object) -> bool:
        """Returns whether two operations are considered equal."""
        param_eq = __o.parameters == self.parameters
        return param_eq and super(ParametricOperation, self).__eq__(__o)

    @property
    def parameters(self):
        """Parameters of the operation."""
        return self._parameters

    @mixedproperty
    def num_parameters(cls) -> int:
        """Number of parameters that the operation requires."""
        if hasattr(cls, "_num_params"):
            return cls._num_params

        raise AttributeError(f"Operations {cls.label} missing class attributes '_num_params'.")

    @classmethod
    def _check_parameters(cls, params):
        """Asserts the size and type of the parameter(s) and returns the
        correct type.

        Args:
            params: Parameters to check.

        Returns:
            list: Sequence of parameters as a list.
        """
        if isinstance(params, str) or not isinstance(params, Sequence):
            params = [params]

        if len(params) != cls._num_params:
            raise ValueError(
                f"Operation '{cls.label} requires "
                f"{cls._num_params} parameters, got {len(params)}."
            )

        # cast to list for convention
        return list(params)

    def __call__(self, qubits: Optional[Sequence[Hashable]] = None):
        """Apply (or reapply) the operation within a context.

        Args:
            qubits: Qubits on which the operation should be applied. Only
                required if not already declared in operation.
        """
        qubits = qubits or self.qubits
        self.__class__(self.parameters, qubits)


class ControlledOperation(Operation):
    """Generic controlled operation.

    Args:
        op: Target operation which is applied to the target qubit.
        control: Qubit(s) on which the target operation is controlled.
        target: Qubit(s) on which the target operation is applied.
    """

    def __init__(
        self,
        op: Operation,
        control: Optional[Union[str, Sequence[str]]] = None,
        target: Optional[Union[str, Sequence[str]]] = None,
    ) -> None:
        # control and target qubits are stored as lists
        if isinstance(control, str) or not isinstance(control, Sequence):
            self._control = [control]
        else:
            self._control = [control]

        if isinstance(target, str) or not isinstance(target, Sequence):
            self._target = [target]
        else:
            self._target = target

        self._target_operation = op

        # all qubits are stored in the 'qubits' attribute
        qubits = self._control + self._target if self._control and self._target else None
        super(ControlledOperation, self).__init__(qubits)

    def __call__(
        self,
        control: Optional[Sequence[Hashable]] = None,
        target: Optional[Sequence[Hashable]] = None,
    ):
        """Apply (or reapply) the operation within a context.

        Args:
            control: Cpntrol qubits. Only required if not already declared in operation.
            target: Target qubits on which the operation should be applied. Only
                required if not already declared in operation.
        """
        control = control or self.control
        target = target or self.target

        self.__class__(control, target)

    @abstractmixedproperty
    def _num_control(cls):
        """Abstract mixedproperty asserting the existence of a ``_num_control`` attribute."""

    @abstractmixedproperty
    def _num_target(cls):
        """Abstract mixedproperty asserting the existence of a ``_num_target`` attribute."""

    @mixedproperty
    def _num_qubits(cls) -> int:
        """Realizing the ``_num_qubits`` mixedproperty so that only ``_num_control`` and
        ``num_target`` attributes are required by subclasses."""
        # BUG: Unless an instance check for ints is here, 'mixedproperty' will complain
        # with 'TypeError: unsupported operand type(s) for +: 'function' and 'function''
        if isinstance(cls.num_control, int) and isinstance(cls.num_target, int):
            return cls.num_control + cls.num_target

        raise AttributeError(
            f"Operations {cls.label} missing class attributes '_num_control' and/or '_num_target'."
        )

    @mixedproperty
    def matrix(cls, self) -> NDArray:
        """The matrix representation of the controlled operation."""
        target_unitary = cls.target_operation.matrix
        num_qubits = getattr(cls, "num_qubits", 2)

        if self:
            control = self.control
            target = self.target
        else:
            num_control = getattr(cls, "num_control", 1)

            control = list(range(num_control))
            target = list(range(num_control, num_qubits))

        matrix = build_controlled_unitary(control, target, target_unitary, num_qubits=num_qubits)
        return matrix

    @property
    def control(self) -> Optional[Union[Hashable, Sequence[Hashable]]]:
        """Control qubit(s)."""
        return self._control

    @property
    def target(self) -> Optional[Union[Hashable, Sequence[Hashable]]]:
        """Target qubit(s)."""
        return self._target

    @mixedproperty
    def num_control(cls) -> int:
        """Number of control qubit(s)."""
        return cls._num_control

    @mixedproperty
    def num_target(cls) -> int:
        """Number of target qubit(s)."""
        return cls._num_target

    @mixedproperty
    def target_operation(cls, self):
        """Target operation"""
        if self is not None:
            return self._target_operation

        return cls._target_operation

    def to_qasm(self):
        """Converts the Controlled operation into an OpenQASM string.

        Returns:
            str: OpenQASM string representation of the Controlled X operation.
        """
        target_str = self.target_operation().to_qasm().split()[0]
        return f"c{target_str} q[{self.control}],  q[{self.target}]"


class Measurement(Operation):
    """Class representing a measurement.

    Args:
        qubits: The qubits which should be measured. Only required when applying
            an measurement within a circuit context.
    """

    def __init__(self, qubits: Optional[Union[Hashable, Sequence[Hashable]]] = None):
        super(Measurement, self).__init__(qubits)

    def to_qasm(self):
        """Converts the measurement into an OpenQASM string.

        Returns:
            str: OpenQASM string representation of the measurement.
        """
        return "measure"


class Barrier(Operation):
    """Class representing a barrier operation.

    Args:
        qubits: Qubits on which the barrier operation should be applied.
            Only required when applying a barrier operation within a circuit
            context.
    """

    def __init__(self, qubits: Optional[Union[Hashable, Sequence[Hashable]]] = None):
        super(Barrier, self).__init__(qubits)

    def to_qasm(self):
        """Converts the barrier into an OpenQASM string.

        Returns:
            str: OpenQASM string representation of the barrier.
        """
        return "barrier"
