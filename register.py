import asyncio
import math
import time
from datetime import timedelta, datetime
from bittensor import Balance
from bittensor_wallet import Wallet
from bittensor.core.async_subtensor import AsyncSubtensor
from bittensor.core.metagraph import AsyncMetagraph
from dotenv import load_dotenv
import os

load_dotenv()

REGISTER_COST_LIMIT = Balance(float(os.getenv("REGISTER_COST_LIMIT")))
WALLET_PWD = os.getenv("WALLET_PASSWORD")


async def register_single_miner(subtensor, wallet, netuid, idx, block_id, block_hash, current_register_cost):
    try:
        print(f"{idx} Start track time: {time.time()}")
        print(f"{idx} Registering hotkey {wallet.hotkey.ss58_address} to netuid {netuid} ...")
        print(f"{idx} Current block number: {block_id}")

        call = await subtensor.substrate.compose_call(
            call_module="SubtensorModule",
            call_function="burned_register",
            call_params={
                "netuid": netuid,
                "hotkey": wallet.hotkey.ss58_address,
            },
        )

        signing_keypair = getattr(wallet, "coldkey")

        extrinsic_data = {
            "call": call,
            "keypair": signing_keypair,
            "era": {"period": 10},
            "tip": 1_000,
        }

        extrinsic = await subtensor.substrate.create_signed_extrinsic(**extrinsic_data)

        response = await subtensor.substrate.submit_extrinsic(
            extrinsic,
            wait_for_inclusion=False,
            wait_for_finalization=False,
        )
        print(f"{idx} End track time: {time.time()}")
    except Exception as e:
        print(f"{idx} Error registering hotkey {wallet.hotkey.ss58_address} to netuid {netuid}: {e}")


async def register_miners_parallel(wallets, subtensor, netuid, next_registration_block):
    block_hash = await subtensor.substrate.get_block_hash(next_registration_block)
    current_register_rao = await subtensor.get_hyperparameter(
        param_name="Burn", netuid=netuid, block_hash=block_hash
    )
    current_register_cost = Balance.from_rao(int(current_register_rao)) if current_register_rao else Balance(0)

    tasks = [
        register_single_miner(
            subtensor=subtensor,
            wallet=wallet,
            netuid=netuid,
            idx=idx,
            block_id=next_registration_block,
            block_hash=block_hash,
            current_register_cost=current_register_cost,
        )
        for idx, wallet in enumerate(wallets)
    ]
    await asyncio.gather(*tasks)


async def register_miner(wallets, network, netuid):
    subtensor = AsyncSubtensor(network=network)
    metagraph = AsyncMetagraph(subtensor=subtensor, netuid=netuid, lite=False)
    await metagraph.sync()

    current_block_number = await subtensor.get_current_block()
    hyperparams = await subtensor.get_subnet_hyperparameters(netuid=netuid)
    last_adjustment_block = await subtensor.substrate.query(
        "SubtensorModule", "LastAdjustmentBlock", [netuid]
    )
    next_registration_block = last_adjustment_block.value + hyperparams.adjustment_interval

    print(f"Next registration block: {next_registration_block}")

    # Wait until the next registration block
    seconds_until_next_block = (next_registration_block - current_block_number) * 12
    await asyncio.sleep(seconds_until_next_block)

    # Register miners in parallel
    await register_miners_parallel(wallets, subtensor, netuid, next_registration_block)


def main():
    netuid = int(os.getenv("NETUID"))

    WALLET_PATH = "~/.bittensor/wallets"
    COLD_KEY = os.getenv("COLD_KEY")
    print(f"here-------------:", COLD_KEY)

    wallets = [
        Wallet(name=COLD_KEY, hotkey="sn90", path=WALLET_PATH),
        Wallet(name=COLD_KEY, hotkey="sn90", path=WALLET_PATH),
        Wallet(name=COLD_KEY, hotkey="sn90", path=WALLET_PATH),
    ]
    for wallet in wallets:
        wallet.coldkey_file.decrypt(WALLET_PWD)  # Decrypt wallets once
        print(f"wallets--------", WALLET_PWD, WALLET_PATH)

    asyncio.run(register_miner(wallets, "finney", netuid))

    # Re-encrypt wallets at the end
    for wallet in wallets:
        wallet.coldkey_file.encrypt(WALLET_PWD)


if __name__ == "__main__":
    main()