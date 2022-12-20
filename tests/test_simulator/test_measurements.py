# Copyright 2022 D-Wave Systems Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

import numpy as np
import pytest

import dwave.gate.operations as ops
from dwave.gate.circuit import Circuit
from dwave.gate.operations.operations import __all__ as all_ops
from dwave.gate.simulator.simulator import simulate


class TestSimulateMeasurements:
    """Unit tests for simulating (mid-circuit) measurements."""

    def test_measurements(self):
        """Test simulating a circuit with a measurement."""
        circuit = Circuit(1, 1)

        with circuit.context as (q, c):
            ops.X(q[0])
            m = ops.Measurement(q[0]) | c[0]

        _ = simulate(circuit)

        assert m.bits
        assert m.bits[0] == c[0]
        assert c[0] == 1

    def test_measurement_state(self):
        """Test accessing a state from a measurement."""
        circuit = Circuit(1, 1)

        with circuit.context as (q, c):
            ops.X(q[0])
            m = ops.Measurement(q[0]) | c[0]

        _ = simulate(circuit)

        assert np.all(m.state == np.array([0, 1]))

    @pytest.mark.parametrize("n", [0, 1, 100])
    def test_measurement_sample(self, n):
        """Test sampling from a measurement."""
        circuit = Circuit(1, 1)

        with circuit.context as (q, c):
            ops.Hadamard(q[0])
            m = ops.Measurement(q[0]) | c[0]

        _ = simulate(circuit)

        samples = m.sample(num_samples=n) or []
        assert len(samples) == n
        assert all([i in (0, 1) for i in samples])

    def test_measurement_sample_multiple_qubits(self):
        """Test sampling from a measurement on multiple qubits."""
        circuit = Circuit(2, 2)

        with circuit.context as (q, c):
            ops.X(q[0])
            m = ops.Measurement(q) | c

        _ = simulate(circuit)

        with pytest.raises(ValueError, match="Must specify which to sample"):
            _ = m.sample()

        assert m.sample(0) == [1]
        assert m.sample(1) == [0]

    def test_measurement_sample_nonexistent_qubit(self):
        """Test sampling from a measurement on a non-existent qubit."""
        circuit = Circuit(1, 1)

        with circuit.context as (q, c):
            ops.X(q[0])
            m = ops.Measurement(q) | c

        _ = simulate(circuit)

        assert m.sample(0) == [1]
        with pytest.raises(ValueError, match="Cannot sample qubit"):
            assert m.sample(1) == [0]

    def test_measurement_expval(self):
        """Test measuring an expectation value from a measurement."""
        circuit = Circuit(1, 1)

        with circuit.context as (q, c):
            ops.Hadamard(q[0])
            m = ops.Measurement(q[0]) | c[0]

        _ = simulate(circuit)
        # expectation values are random; assert that it's between 0.4 and 0.6
        assert 0.5 == pytest.approx(m.expval(), 0.2)

    def test_measurement_no_simulation(self):
        """Test a circuit with a measurement without simulating it."""
        circuit = Circuit(1, 1)

        with circuit.context as (q, c):
            ops.Hadamard(q[0])
            m = ops.Measurement(q[0])

        assert m.expval() is None
        assert m.sample() is None
        assert m.state is None
