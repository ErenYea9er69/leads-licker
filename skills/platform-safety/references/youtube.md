# YouTube

## What the app does

- Searches videos. With YOUTUBE_API_KEY it uses the YouTube Data API v3 and learns the comment count, the language, whether the video is live, public and open to comments. Without a key it lists videos through the web search chain and marks them unverified.
- Reads the top comments of a video. These are the reply targets. It needs the key.
- Reads the transcript with the youtube-transcript-api package (pip install "agent-reach[youtube]"). It prefers the owner's language. When the video has another language, it asks YouTube to translate the transcript when the channel allows it. The note on the transcript says whether it is auto-generated or uploaded and whether it was translated.
- Gives the writer a short transcript excerpt as background. The writer may use only what the excerpt says. It must not describe the video beyond it or quote a timestamp the excerpt does not list.

## What the app never does

- It never posts to YouTube. Writing comments through the API needs OAuth consent for the channel, and the app holds none. The owner pastes each comment from the channel's own account. The app gives the link that opens the video with the comment highlighted.
- It never reads comments from a video with comments turned off, from children's content, from live streams or from private videos.

## Limits

- Quota. A search costs 100 units, a video lookup or a comment page costs 1. Google grants 10,000 units a day by default. The app counts its own spending and stops at YOUTUBE_DAILY_QUOTA (default 9000). Run `agent-reach discovery check youtube` to see the count.
- Transcripts come from YouTube's own pages. YouTube blocks some networks (cloud servers especially). A blocked read is reported as blocked. The search still works.
- A channel can turn transcripts off. The video still counts as a lead when its comments qualify.

## Reply style

- One short comment, under 70 words. Start from a detail of the video or of the comment you answer. No links, no "great video", no emoji unless the owner uses them.
- A reply to a viewer's comment reads best. A reply to the video itself fits a question the video leaves open.
- A video takes one reply from the owner's accounts, and a second only under another viewer's comment, with the thread rules.

## Accounts

The owner links a channel by its handle. With the key, the app reads the channel's age and size. The Data API lists no comments by author, so the voice comes from samples the owner pastes.
