import asyncio
import telegram

async def main():
    bot = telegram.Bot("7998479938:AAGK2rhGr9u-E6fQSciZXdi80REGwwonnGU")
    async with bot:
        print(await bot.get_me())


if __name__ == '__main__':
    asyncio.run(main())
