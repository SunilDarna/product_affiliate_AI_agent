# Product Affiliate AI Agent: Redefined Context & Requirements

## Core Objective
Build a fully autonomous AI agent that identifies trending products in India, curates promotional video clips, edits and dubs them with AI voiceovers, generates dynamic affiliate links, and publishes them to YouTube Shorts and Instagram Reels to generate affiliate income.

## Technical Foundation & Constraints
- **LLM Endpoint**: MUST use the same online LLM endpoint/API as established in the `ShortsAutomatorAIAgent` project (using Google Gemini API via `llm_api_key`), rather than a local Docker LLM.
- **Cost Efficiency**: MUST prioritize free services and local resources where possible.
- **Reference Architecture**: MUST use the existing `/Users/sunildarna/Documents/AI-income-generator/ShortsAutomatorAIAgent` project as a structural and functional reference to recreate necessary components.
- **Main Workspace**: MUST develop all new code within `/Users/sunildarna/Documents/AI-income-generator/product_affiliate_AI_agent`.
- **Credential Management**: MUST store all API keys and credentials in a centralized `secrets.json` file for easy updating.

## Autonomous Workflow Requirements

### 1. Trend & Product Discovery
- MUST identify real-time trending products with high demand in India across all internet sources.
- MUST scrape and analyze affiliate networks (Flipkart, Amazon, Meesho, Myntra) to determine commission rates.
- MUST filter and select a list of products offering the highest return percentages.

### 2. Video Sourcing & Script Generation
- MUST search YouTube for official product advertisements related to the selected products.
- MUST download a relevant video clip under 58 seconds in duration.
- MUST remove the original audio track from the downloaded clip.
- MUST generate 4-5 variant scripts using the online LLM. Scripts MUST include strong hooks and engaging storytelling tailored to the specific product and current trends.

### 3. Voiceover Generation
- MUST concentrate strictly on English voiceovers for the initial phase. (Keep a space/architecture ready for future enhancements into Telugu, Hindi, Tamil, Kannada, Malayalam, and Sarvam AI integration).
- MUST generate voiceovers utilizing free services (e.g., Edge TTS), ElevenLabs AI (if free quota permits), or a custom local text-to-speech service running in Docker.
- MUST ensure the generated voiceover features adaptive content based on real-time trends to perfectly match the video clip's context.

### 4. Video Editing & Composition
- MUST programmatically edit the video clip to overlay the generated voiceover.
- MUST synchronize the voiceover timing to match the visual pacing of the clip.
- MUST generate and burn dynamic subtitles onto the video using an online/local model.

### 5. Monetization & Publishing
- MUST dynamically generate an affiliate link for each product by automating a Chrome session utilizing your already-logged-in Amazon account.
- MUST generate SEO 2.0 optimized titles, descriptions, and hashtags using the online LLM based on real-time trends.
- MUST include the dynamic affiliate link in the video description and title.
- MUST automatically upload the finalized video to the designated YouTube channel (using API credentials from the reference project) and eventually to Instagram (credentials to be added later).
