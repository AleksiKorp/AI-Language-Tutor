/**
 * CONVERSATION INFO DISPLAYED - Frontend Text Configuration
 *
 * This file contains all the text content displayed in the frontend UI.
 *
 */

export const CONVERSATION_INFO_DISPLAYED = {
  pageTitle: "AI Language Tutor",
  visualizerType: "plasma",
};

// TypeScript type for topic info
export type TopicInfo = {
  description: string;
  details: string[];
  link: string;
  image?: string; // Optional image URL
};
