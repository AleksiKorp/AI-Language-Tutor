/**
 * CONVERSATION INFO DISPLAYED - Frontend Text Configuration
 *
 * This file contains ALL the text content displayed in the frontend UI.
 * Edit this file to customize topic names, descriptions, details, links, and page title.
 *
 * IMPORTANT: Topic names here MUST match the TOPICS list in backend/conversation_config.py
 * The backend uses topic names to track conversation progress, so they must be identical.
 *
 * How to customize for a different domain (e.g., cooking, shopping):
 * 1. Change pageTitle to your domain name
 * 2. Replace topic names with your domain topics (same as backend config)
 * 3. Update descriptions and details for each topic
 * 4. Set links (use empty string "" if no link needed)
 *
 * Example for a cooking assistant:
 *   pageTitle: "Home Cooking Assistant"
 *   topics: {
 *     "Breakfast Recipes": { description: "...", details: [...], link: "..." }
 *     "Lunch Ideas": { description: "...", details: [...], link: "" }
 *   }
 */

export const CONVERSATION_INFO_DISPLAYED = {

  // ============================================================================
  // PAGE TITLE
  // ============================================================================
  // This appears in:
  // - Browser tab title
  // - Top header bar of the application
  pageTitle: "AI Language Tutor",

  // ============================================================================
  // VISUALIZER CONFIGURATION
  // ============================================================================
  // Choose which visualizer to display:
  // - "plasma": Animated plasma orb (default, colorful and dynamic)
  // - "waveform": Custom waveform bars (mic + bot audio)
  visualizerType: "plasma",

  // ============================================================================
  // TOPIC INFORMATION
  // ============================================================================
  // IMPORTANT: When adding/removing topics, update BOTH this file AND backend/conversation_config.py
  //
  // Each topic has three parts:
  //
  // 1. TOPIC NAME (the key, e.g., "Lectures & Schedule")
  //    - Must match exactly with backend TOPICS in conversation_config.py
  //    - Displayed on topic cards in the UI
  //    - Used by assistant to track which topics were discussed
  //
  // 2. description (string)
  //    - Short summary shown on the topic card
  //    - Appears when user shows interest in the topic
  //
  // 3. details (array of strings)
  //    - List of specific information items
  //    - Each string becomes a bullet point
  //    - Displayed in expanded view when user is interested
  //
  // 4. link (string)
  //    - URL to external resource (e.g., Moodle, documentation)
  //    - If empty string "", no link button will be shown
  //    - If provided, shows "Open in Moodle" button
  //
  // 5. image (string, optional)
  //    - URL to an image (can be external URL or local path in /public folder)
  //    - If empty string "", no image will be shown
  //    - Displayed above the details list
  //    - Example: "https://example.com/image.jpg" or "/images/schedule.png"
  //
  topics: {
    "Lectures & Schedule": {
      description: "8 lectures from January to May 2026, Mondays 13:15-15:30",
      details: [
        "Jan 19 - Course intro (Pinni B4113)",
        "Jan 26 - Voice UIs (Paatalo C113)",
        "Feb 9 - UX Design (Pinni B4113)",
        "Mar 2 - Guest: Kristiina Jokinen",
        "Mar 9 - Architecture (Pinni B1083)",
        "Mar 30 - Error Handling (Pinni B1083)",
        "Apr 13 - Ethics & Future (Pinni B1083)",
        "May 11 - Final Presentations (Pinni B4113)"
      ],
      link: "https://moodle.tuni.fi/course/view.php?id=56424",
      image: "https://images.unsplash.com/photo-1506784983877-45594efa4cbe?w=800&h=400&fit=crop" // Calendar/schedule image
    },
    "Vocabulary practice": {
      description: "Practice vocabulary",
      details: [
        "practice"
      ],
      link: "",
      image: ""
    },
    "Grammar Drills": {
      description: "Practice vocabulary",
      details: [
        "Drill"
      ],
      link: "",
      image: ""
    },
    "Free Conversation": {
      description: "Practice vocabulary",
      details: [
        "Talking.."
      ],
      link: "",
      image: ""
    }
  }
};

// TypeScript type for topic info
export type TopicInfo = {
  description: string;
  details: string[];
  link: string;
  image?: string; // Optional image URL
};
