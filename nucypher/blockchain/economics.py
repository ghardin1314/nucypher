"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""


from decimal import Decimal, localcontext
from typing import Tuple

from math import log

from nucypher.blockchain.eth.token import NU


LOG2 = Decimal(log(2))


class TokenEconomics:
    """
    Parameters to use in token and escrow blockchain deployments
    from high-level human-understandable parameters.

    --------------------------

    Formula for staking in one period:
    (totalSupply - currentSupply) * (lockedValue / totalLockedValue) * (k1 + allLockedPeriods) / k2

    K2 - Staking coefficient
    K1 - Locked periods coefficient

    if allLockedPeriods > maximum_rewarded_periods then allLockedPeriods = maximum_rewarded_periods
    kappa * log(2) / halving_delay === (k1 + allLockedPeriods) / k2

    """

    # Token Denomination
    __token_decimals = 18
    nunits_per_token = 10 ** __token_decimals  # Smallest unit designation

    # Period Definition
    __default_hours_per_period = 24

    # Time Constraints
    __default_minimum_worker_periods = 2
    __default_minimum_locked_periods = 30  # 720 Hours minimum

    # Value Constraints
    __default_minimum_allowed_locked = NU(15_000, 'NU').to_nunits()
    __default_maximum_allowed_locked = NU(4_000_000, 'NU').to_nunits()

    def __init__(self,
                 initial_supply: int,
                 total_supply: int,
                 staking_coefficient: int,
                 locked_periods_coefficient: int,
                 maximum_rewarded_periods: int,
                 hours_per_period: int = __default_hours_per_period,
                 minimum_locked_periods: int = __default_minimum_locked_periods,
                 minimum_allowed_locked: int = __default_minimum_allowed_locked,
                 maximum_allowed_locked: int = __default_maximum_allowed_locked,
                 minimum_worker_periods: int = __default_minimum_worker_periods
                 ):
        """
        :param initial_supply: Tokens at t=0
        :param total_supply: Tokens at t=8
        :param staking_coefficient: K2
        :param locked_periods_coefficient: K1
        :param maximum_rewarded_periods: Max periods that will be additionally rewarded
        :param hours_per_period: Hours in single period
        :param minimum_locked_periods: Min amount of periods during which tokens can be locked
        :param minimum_allowed_locked: Min amount of tokens that can be locked
        :param maximum_allowed_locked: Max amount of tokens that can be locked
        :param minimum_worker_periods: Min amount of periods while a worker can't be changed
        """

        self.initial_supply = initial_supply
        # Remaining / Reward Supply - Escrow Parameter
        self.reward_supply = total_supply - initial_supply
        self.total_supply = total_supply
        self.staking_coefficient = staking_coefficient
        self.locked_periods_coefficient = locked_periods_coefficient
        self.maximum_rewarded_periods = maximum_rewarded_periods
        self.hours_per_period = hours_per_period
        self.minimum_locked_periods = minimum_locked_periods
        self.minimum_allowed_locked = minimum_allowed_locked
        self.maximum_allowed_locked = maximum_allowed_locked
        self.minimum_worker_periods = minimum_worker_periods
        self.seconds_per_period = hours_per_period * 60 * 60  # Seconds in single period

    @property
    def erc20_initial_supply(self) -> int:
        return int(self.initial_supply)

    @property
    def erc20_reward_supply(self) -> int:
        return int(self.reward_supply)

    @property
    def erc20_total_supply(self) -> int:
        return int(self.total_supply)

    @property
    def staking_deployment_parameters(self) -> Tuple[int, ...]:
        """Cast coefficient attributes to uint256 compatible type for solidity+EVM"""
        deploy_parameters = (

            # Period
            self.hours_per_period,            # Hours in single period

            # Coefficients
            self.staking_coefficient,         # Staking coefficient (k2)
            self.locked_periods_coefficient,  # Locked periods coefficient (k1)
            self.maximum_rewarded_periods,    # Max periods that will be additionally rewarded (awarded_periods)

            # Constraints
            self.minimum_locked_periods,      # Min amount of periods during which tokens can be locked
            self.minimum_allowed_locked,      # Min amount of tokens that can be locked
            self.maximum_allowed_locked,      # Max amount of tokens that can be locked
            self.minimum_worker_periods       # Min amount of periods while a worker can't be changed
        )
        return tuple(map(int, deploy_parameters))


class StandardTokenEconomics(TokenEconomics):
    """
    Calculate parameters to use in token and escrow blockchain deployments
    from high-level human-understandable parameters.

    --------------------------

    Formula for staking in one period:
    (totalSupply - currentSupply) * (lockedValue / totalLockedValue) * (k1 + allLockedPeriods) / k2

    K2 - Staking coefficient
    K1 - Locked periods coefficient

    if allLockedPeriods > maximum_rewarded_periods then allLockedPeriods = maximum_rewarded_periods
    kappa * log(2) / halving_delay === (k1 + allLockedPeriods) / k2

    ...but also...

    kappa = small_stake_multiplier + (1 - small_stake_multiplier) * min(T, T1) / T1
    where allLockedPeriods == min(T, T1)

    --------------------------

    Academic Reference:

    NuCypher: Mining & Staking Economics - Michael Egorov, MacLane Wilkison, NuCypher
    <https://github.com/nucypher/mining-paper/blob/master/mining-paper.pdf>

    """

    # Decimal
    _precision = 28

    # Supply
    __default_initial_supply = NU(int(1_000_000_000), 'NU').to_nunits()
    __default_initial_inflation = 1
    __default_token_halving = 2      # years
    __default_reward_saturation = 1  # years
    __default_small_stake_multiplier = Decimal(0.5)

    def __init__(self,
                 initial_supply: int = __default_initial_supply,
                 initial_inflation: int = __default_initial_inflation,
                 halving_delay: int = __default_token_halving,
                 reward_saturation: int = __default_reward_saturation,
                 small_stake_multiplier: Decimal = __default_small_stake_multiplier
                 ):
        """
        :param initial_supply: Tokens at t=0
        :param initial_inflation: Inflation on day 1 expressed in units of year**-1
        :param halving_delay: Time for inflation halving in years
        :param reward_saturation: "saturation" time - if staking is longer than T_sat, the reward doesn't get any higher
        :param small_stake_multiplier: Fraction of maximum reward rate paid to those who are about to unlock tokens
        """

        #
        # Calculate
        #

        with localcontext() as ctx:
            ctx.prec = self._precision

            initial_supply = Decimal(initial_supply)

            # ERC20 Token parameter (See Equation 4 in Mining paper)
            total_supply = initial_supply * (1 + initial_inflation * halving_delay / LOG2)

            # k2 - Escrow parameter
            staking_coefficient = 365 ** 2 * reward_saturation * halving_delay / LOG2 / (1 - small_stake_multiplier)

            # k1 - Escrow parameter
            locked_periods_coefficient = 365 * reward_saturation * small_stake_multiplier / (1 - small_stake_multiplier)

            # Awarded periods- Escrow parameter
            maximum_rewarded_periods = reward_saturation * 365

        # Injected
        self.initial_inflation = initial_inflation
        self.token_halving = halving_delay
        self.token_saturation = reward_saturation
        self.small_stake_multiplier = small_stake_multiplier

        super(StandardTokenEconomics, self).__init__(
            initial_supply,
            total_supply,
            staking_coefficient,
            locked_periods_coefficient,
            maximum_rewarded_periods
        )

    def token_supply_at_period(self, period: int) -> int:
        if period < 0:
            raise ValueError("Period must be a positive integer")

        with localcontext() as ctx:
            ctx.prec = self._precision

            # Eq. 3 of the mining paper
            # https://github.com/nucypher/mining-paper/blob/master/mining-paper.pdf
            t = Decimal(period)
            S_0 = self.erc20_initial_supply
            i_0 = 1
            I_0 = i_0 * S_0  # in 1/years
            T_half = self.token_halving  # in years
            T_half_in_days = T_half * 365

            S_t = S_0 + I_0 * T_half * (1 - 2**(-t / T_half_in_days)) / LOG2
            return int(S_t)

    def cumulative_rewards_at_period(self, period: int) -> int:
        return self.token_supply_at_period(period) - self.erc20_initial_supply

    def rewards_during_period(self, period: int) -> int:
        return self.cumulative_rewards_at_period(period) - self.cumulative_rewards_at_period(period-1)


class SlashingEconomics:

    HASH_ALGORITHM_KECCAK256 = 0
    HASH_ALGORITHM_SHA256 = 1
    HASH_ALGORITHM_RIPEMD160 = 2

    hash_algorithm = HASH_ALGORITHM_SHA256
    base_penalty = 100
    penalty_history_coefficient = 10
    percentage_penalty_coefficient = 8
    reward_coefficient = 2

    @property
    def deployment_parameters(self) -> Tuple[int, ...]:
        """Cast coefficient attributes to uint256 compatible type for solidity+EVM"""

        deployment_parameters = [
            self.hash_algorithm,
            self.base_penalty,
            self.penalty_history_coefficient,
            self.percentage_penalty_coefficient,
            self.reward_coefficient
        ]

        return tuple(map(int, deployment_parameters))
