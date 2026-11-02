/** @type {import('@docusaurus/plugin-content-docs').SidebarsConfig} */
const sidebars = {
	tutorialSidebar: [
		{
			type: "category",
			label: "Introduction",
			items: ["intro"],
		},
		{
			type: "category",
			label: "Quickstart",
			items: ["quickstart/docker"],
		},
		{
			type: "category",
			label: "API Reference",
			items: ["api/wallet-generation"],
		},
		{
			type: "category",
			label: "MCP Server",
			items: ["mcp/overview"],
		},
		{
			type: "category",
			label: "x402 Marketplace",
			items: ["x402/overview"],
		},
		{
			type: "category",
			label: "WordPress Plugin",
			items: ["wordpress/overview"],
		},
		{
			type: "category",
			label: "CLI",
			items: ["cli/overview"],
		},
		{
			type: "category",
			label: "Security",
			items: ["security/overview"],
		},
		{
			type: "category",
			label: "Resources",
			items: ["changelog", "faq", "chains-supported", "security-overview"],
		},
	],
};

module.exports = sidebars;
