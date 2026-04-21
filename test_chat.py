import asyncio
import websockets
import json

async def test_chat():
    uri = "ws://localhost:8000/ws"
    
    # Alice joins and sends a message
    async with websockets.connect(uri) as ws1:
        await ws1.recv() # Connected message
        await ws1.send(json.dumps({'type': 'join', 'username': 'Alice'}))
        await ws1.recv() # Alice joined message
        await ws1.send(json.dumps({'type': 'message', 'content': 'Hello from Alice'}))
        resp = await ws1.recv()
        print("ws1 received:", resp)
        
    print("Alice disconnected.")

    # Bob joins, sends a message (he shouldn't get Alice's message as history yet, because he joins AFTER she sends it... wait, he will get Alice's message if she sent it before he joined, actually history gets all messages from when Bob first joined? Oh, wait, the db query is `timestamp >= user.joined_at`. If Bob joins at t=1, he won't see Alice's msg. But if Bob was new, his joined_at is now, so he sees nothing previous. Wait, let's see.)
    async with websockets.connect(uri) as ws2:
        await ws2.recv() # Connected message
        await ws2.send(json.dumps({'type': 'join', 'username': 'Bob'}))
        # Receive history for Bob
        while True:
            msg = await ws2.recv()
            if "Bob joined" in msg:
                break
            print("Bob received history/msg:", msg)
        await ws2.send(json.dumps({'type': 'message', 'content': 'Bob says hi'}))
        print("Bob sent message.")
        
    print("Bob disconnected.")

    # Alice rejoins
    async with websockets.connect(uri) as ws3:
        await ws3.recv()
        await ws3.send(json.dumps({'type': 'join', 'username': 'Alice'}))
        
        # Read history
        print("--- Alice Re-join History ---")
        while True:
            try:
                msg = await asyncio.wait_for(ws3.recv(), timeout=1.0)
                print("Alice Re-Join:", msg)
            except asyncio.TimeoutError:
                break

if __name__ == "__main__":
    asyncio.run(test_chat())
