// Constants and configuration
const API_HOST = window.location.origin;
const INACTIVITY_TIMEOUT = 5 * 60 * 1000; // 5 minutes

// Entity patterns for linking
const ENTITY_PATTERNS = [
  { pattern: /\bTreasury\b/g, key: 'treasury' },
  { pattern: /\bNIH\b/g, key: 'nih' },
  { pattern: /\bFDA\b/g, key: 'fda' },
  { pattern: /\bUSDA\b/g, key: 'usda' },
  { pattern: /\bFSIS\b/g, key: 'usda' },
  { pattern: /\bDOT\b/g, key: 'dot' },
  { pattern: /\bSEC\b/g, key: 'sec' },
  { pattern: /\bHHS\b/g, key: 'hhs' },
  { pattern: /\bUSAID\b/g, key: 'usaid' },
  { pattern: /\bVanguard\b/gi, key: 'vanguard' },
  { pattern: /\bMastercard\b/gi, key: 'mastercard' },
  { pattern: /\bBlue Cross\b/gi, key: 'bcbs' },
  { pattern: /\bWorld Bank\b/gi, key: 'worldbank' },
  { pattern: /\bBillboard\b/gi, key: 'billboard' },
  { pattern: /\bNational Gallery\b/gi, key: 'nga' },
  { pattern: /\bDrupal\b/gi, key: 'drupal' },
  { pattern: /\bKubernetes\b/gi, key: 'kubernetes' },
  { pattern: /\bAzure\b/gi, key: 'azure' },
  { pattern: /\bAWS\b/g, key: 'aws' },
];

// Image mappings for topics
const IMAGE_MAPPINGS = {
  treasury: { src: '/static/images/treasury.png', alt: 'U.S. Department of Treasury', category: 'Federal Agency' },
  nih: { src: '/static/images/nih.png', alt: 'National Institutes of Health', category: 'Federal Agency' },
  fda: { src: '/static/images/fda.png', alt: 'Food & Drug Administration', category: 'Federal Agency' },
  usda: { src: '/static/images/usda.png', alt: 'USDA Food Safety', category: 'Federal Agency' },
  dot: { src: '/static/images/transportation2.png.webp', alt: 'Department of Transportation', category: 'Federal Agency' },
  sec: { src: '/static/images/sec.png', alt: 'Securities & Exchange Commission', category: 'Federal Agency' },
  hhs: { src: '/static/images/hhs.png', alt: 'Health & Human Services', category: 'Federal Agency' },
  usaid: { src: '/static/images/usaid.png', alt: 'USAID', category: 'Federal Agency' },
  vanguard: { src: '/static/images/vanguard.png', alt: 'Vanguard', category: 'Enterprise Client' },
  mastercard: { src: '/static/images/mastercard.png', alt: 'Mastercard', category: 'Enterprise Client' },
  bcbs: { src: '/static/images/bcbs.png', alt: 'Blue Cross Blue Shield', category: 'Enterprise Client' },
  worldbank: { src: '/static/images/worldbank.png', alt: 'World Bank', category: 'International' },
  billboard: { src: '/static/images/billboard.png', alt: 'Billboard', category: 'Media' },
  nga: { src: '/static/images/nga.png.webp', alt: 'National Gallery of Art', category: 'Cultural Institution' },
  drupal: { src: '/static/images/drupal.png', alt: 'Drupal', category: 'Technology' },
  kubernetes: { src: '/static/images/kubernetes.png', alt: 'Kubernetes', category: 'Technology' },
  azure: { src: '/static/images/azure.png', alt: 'Microsoft Azure', category: 'Cloud Platform' },
  aws: { src: '/static/images/aws.png', alt: 'Amazon Web Services', category: 'Cloud Platform' },
};
