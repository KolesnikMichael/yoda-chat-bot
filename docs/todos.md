- AffectProvider: should return current emotional state as a string, and MemoryCore should pass it to MemoryProvider and it should append it to the conversation as a system message
- Intent is identified on each user message? If so, it's not efficient both token-wise (could we make Yoda signalling instead?), and quality wise (intent could be scattered across several messagess)
- There's some woodoo going on in Cognition's extract_user_text
- Think about session recovery during application restart
- ReAct loop doesn't survive tool crashes like exception when using ask_user
- Calculating timezone can be done when user provides his current time
- There are countries that do not use daylight saving


