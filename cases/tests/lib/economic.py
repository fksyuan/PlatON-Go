from decimal import Decimal

from dacite import from_dict
from .utils import wait_block_number
from environment.node import Node
from .genesis import Genesis
from common.key import get_pub_key
import math
from .config import EconomicConfig
from environment.env import TestEnvironment


class Economic:
    cfg = EconomicConfig

    def __init__(self, env: TestEnvironment):
        self.env = env

        self.genesis = from_dict(data_class=Genesis, data=self.env.genesis_config)

        # Block rate parameter
        self.per_round_blocks = self.genesis.config.cbft.amount
        self.interval = int((self.genesis.config.cbft.period / self.per_round_blocks) / 1000)

        # Length of additional issuance cycle
        self.additional_cycle_time = self.genesis.EconomicModel.Common.AdditionalCycleTime

        # Number of verification
        self.validator_count = self.genesis.EconomicModel.Common.MaxConsensusVals

        # Billing related
        # Billing cycle
        self.expected_minutes = self.genesis.EconomicModel.Common.MaxEpochMinutes
        # Consensus rounds
        self.consensus_wheel = (self.expected_minutes * 60) // (
                    self.interval * self.per_round_blocks * self.validator_count)
        # Number of settlement periods
        self.settlement_size = self.consensus_wheel * (self.interval * self.per_round_blocks * self.validator_count)
        # Consensus round number
        self.consensus_size = self.interval * self.per_round_blocks * self.validator_count

        # Minimum amount limit
        # Minimum deposit amount
        self.create_staking_limit = self.genesis.EconomicModel.Staking.StakeThreshold
        # Minimum holding amount
        self.add_staking_limit = self.genesis.EconomicModel.Staking.OperatingThreshold
        # Minimum commission amount
        self.delegate_limit = self.add_staking_limit
        # unstaking freeze duration
        self.unstaking_freeze_ratio = self.genesis.EconomicModel.Staking.UnStakeFreezeDuration
        #ParamProposalVote_DurationSeconds
        self.pp_vote_settlement_wheel = self.genesis.EconomicModel.Gov.ParamProposalVote_DurationSeconds // (
                (self.interval * self.per_round_blocks * self.validator_count) * self.consensus_wheel
        )
        #slash blocks reward
        self.slash_blocks_reward = self.genesis.EconomicModel.Slashing.SlashBlocksReward


    @property
    def account(self):
        return self.env.account

    def get_block_count_number(self, node: Node, roundnum=1):
        """
        Get the number of blocks out of the verification node
        """
        current_block = node.eth.blockNumber
        block_namber = self.consensus_size * roundnum
        count = 0
        for i in range(block_namber - 1):
            node_id = get_pub_key(node.url, current_block)
            current_block = current_block - 1
            if node_id == node.node_id:
                count = count + 1
        return count

    def get_current_year_reward(self, node: Node, verifier_num=None):
        """
        Get the first year of the block reward, pledge reward
        :return:
        """
        new_block_rate = self.genesis.EconomicModel.Reward.NewBlockRate
        annualcycle, annual_size, current_end_block = self.get_annual_switchpoint(node)
        if verifier_num is None:
            verifier_list = node.ppos.getVerifierList()
            verifier_num = len(verifier_list['Ret'])
        print('verifier_num', verifier_num)
        amount = node.eth.getBalance(self.cfg.INCENTIVEPOOL_ADDRESS, 0)
        block_proportion = str(new_block_rate / 100)
        staking_proportion = str(1 - new_block_rate / 100)
        block_reward = int(Decimal(str(amount)) * Decimal(str(block_proportion)) / Decimal(str(annual_size)))
        staking_reward = int(
            Decimal(str(amount)) * Decimal(str(staking_proportion)) / Decimal(str(annualcycle)) / Decimal(
                str(verifier_num)))
        # staking_reward = amount - block_reward
        return block_reward, staking_reward

    def get_settlement_switchpoint(self, node: Node, number=0):
        """
        Get the last block of the current billing cycle
                :param node: node object
                :param number: number of billing cycles
        :return:
        """
        block_number = self.settlement_size * number
        tmp_current_block = node.eth.blockNumber
        current_end_block = math.ceil(tmp_current_block / self.settlement_size) * self.settlement_size + block_number
        return current_end_block

    def get_front_settlement_switchpoint(self, node: Node, number=0):
        """
        Get a block height before the current billing cycle
                :param node: node object
                :param number: number of billing cycles
        :return:
        """
        block_num = self.settlement_size * (number + 1)
        current_end_block = self.get_settlement_switchpoint(node)
        history_block = current_end_block - block_num
        return history_block

    def wait_settlement_blocknum(self, node: Node, number=0):
        """
        Waiting for a billing cycle to settle
                :param node:
                :param number: number of billing cycles
        :return:
        """
        end_block = self.get_settlement_switchpoint(node, number)
        wait_block_number(node, end_block, self.interval)

    def get_annual_switchpoint(self, node: Node):
        """
        Get the number of annual settlement cycles
        """
        annual_cycle = (self.additional_cycle_time * 60) // (self.settlement_size * self.interval)
        annualsize = annual_cycle * self.settlement_size
        current_block = node.eth.blockNumber
        current_end_block = math.ceil(current_block / annualsize) * annualsize
        return annual_cycle, annualsize, current_end_block

    def wait_annual_blocknum(self, node: Node):
        """
        Waiting for the end of the annual block high
        """
        annualcycle, annualsize, current_end_block = self.get_annual_switchpoint(node)
        current_block = node.eth.blockNumber
        differ_block = annualsize - (current_block % annualsize)
        annual_end_block = current_block + differ_block
        wait_block_number(node, annual_end_block, self.interval)

    def wait_consensus_blocknum(self, node: Node, number=0):
        """
        Waiting for a consensus round to end
        """
        end_block = self.get_consensus_switchpoint(node, number)
        wait_block_number(node, end_block, self.interval)

    def get_consensus_switchpoint(self, node: Node, number=0):
        """
        Get the specified consensus round high
        """
        block_number = self.consensus_size * number
        current_block = node.eth.blockNumber
        current_end_block = math.ceil(current_block / self.consensus_size) * self.consensus_size + block_number
        return current_end_block


if __name__ == '__main__':
    a = Economic()
    a.get_current_year_reward()