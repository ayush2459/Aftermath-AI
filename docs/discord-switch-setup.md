# Discord to Switch: first integration milestone

Switch owns the Discord bot connection. Do not add a second Discord gateway client or a Discord webhook receiver to the Aftermath backend. The first milestone is a Discord channel that appears as a Switch room and can carry messages in both directions. The backend agent joins that room in the next milestone.

## Prerequisites

- A Discord server where you can add a bot and manage channels.
- Admin access to a Switch server in Switch Console.
- A private Discord channel for testing with synthetic orders. Switch rooms are channels, not Discord DMs.

## 1. Create the Discord application

1. In the [Discord Developer Portal](https://discord.com/developers/applications), create an application and open **Bot**. Copy its bot token into a local secret store. Do not commit it or paste it into a ticket or chat.
2. Enable **Server Members Intent** and **Message Content Intent**, then save. Switch needs the latter to receive the text sent to agents.
3. Under **OAuth2 → URL Generator**, select the `bot` and `applications.commands` scopes.
4. Grant the bot: View Channels, Send Messages, Send Messages in Threads, Manage Webhooks, Manage Channels, Manage Roles, Read Message History, Attach Files, and Add Reactions. Invite it using the generated URL. Switch uses per-channel webhooks to post as each agent.
5. In Discord, enable **User Settings → Advanced → Developer Mode**, then copy the server ID. Switch calls this the **Guild Id**.

## 2. Connect Discord in Switch Console

1. Select your Switch server in the Console sidebar and open its **Home** page.
2. Under **Messaging apps**, choose **Connect → Discord**.
3. Name the connection, enter the bot token and Guild Id, and select **Connect**. Switch should report a bad token immediately.
4. Link your own Discord account when prompted. This lets Switch recognize you as the owner of agents you add later.

Switch opens the connection to Discord; the Aftermath API needs no public Discord callback URL.

## 3. Verify the Discord → Switch path

1. Post an ordinary message in the private test channel, such as `Switch connection test`.
2. Confirm the channel appears under **Your Rooms** in Switch Console. Discord posting creates the Switch room; adding the bot alone does not.
3. Confirm the Discord connection appears under **Messaging apps** with no error.
4. Type `/` in the channel and check that Switch commands are offered. Commands alone do not prove that the channel is a room, so also check **Your Rooms**.
5. Record the room name and Switch server's **agent bridge base URL** for the next milestone. The agent bridge is usually different from the Console/Gateway URL. `GET <bridge-base-url>/health` should succeed without a token.

At this point Discord is connected to Switch. The order-status agent is not yet needed to prove this milestone.

## Next milestone: Switch → Aftermath backend

Register an Aftermath support agent with Switch's [custom agent protocol](https://docs.switchagents.ai/switch-rooms/internals/agent-protocol), invite it to the Discord-backed room, and run its WebSocket client. The client will act only on messages Switch marks `addressed`, call a read-only backend order-status tool, and post the answer through Switch. Require proof that the requester owns the order before exposing order details. The backend remains the source of truth for payment, fulfillment, and incident status.

## Troubleshooting

- **No message text reaches Switch:** check that Message Content Intent is enabled and saved.
- **Bot cannot reply as an agent:** check Manage Webhooks and Send Messages in Threads.
- **Slash commands missing:** re-invite with `applications.commands`, then restart the connection.
- **Channel absent from Your Rooms:** post a normal message in it; merely adding the bot is insufficient.
- **Agent cannot recognize you later:** link your Discord account in Switch Console.

Source: [Switch's Discord setup guide](https://docs.switchagents.ai/switch-rooms/deploy/messaging-apps/discord).
