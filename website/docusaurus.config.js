module.exports = {
	title: "WalletPress",
	tagline: "55-Chain Wallet Infrastructure You Self-Host",
	url: "https://docs.walletpress.cc",
	baseUrl: "/",
	onBrokenLinks: "warn",
	favicon: "img/favicon.ico",
	organizationName: "RugMunchMedia",
	projectName: "walletpress",
	themeConfig: {
		navbar: {
			title: "WalletPress",
			logo: {
				alt: "WalletPress Logo",
				src: "img/logo.svg",
				href: "/docs/intro",
			},
			items: [
				{ to: "/docs/intro", label: "Docs", position: "left" },
				{ to: "/docs/api/wallet-generation", label: "API", position: "left" },
				{ to: "/docs/mcp/overview", label: "MCP", position: "left" },
				{ to: "/docs/x402/overview", label: "x402", position: "left" },
				{
					to: "/docs/wordpress/overview",
					label: "WordPress",
					position: "left",
				},
				{ to: "/docs/cli/overview", label: "CLI", position: "left" },
				{
					href: "https://git.rugmunch.io/RugMunchMedia/walletpress",
					label: "GitHub",
					position: "right",
				},
				{
					href: "https://walletpress.cc",
					label: "Website",
					position: "right",
				},
			],
		},
		footer: {
			style: "dark",
			links: [
				{
					title: "Docs",
					items: [
						{ label: "Quickstart", to: "/docs/intro" },
						{ label: "API Reference", to: "/docs/api/wallet-generation" },
						{ label: "MCP Server", to: "/docs/mcp/overview" },
						{ label: "x402 Payments", to: "/docs/x402/overview" },
						{ label: "WordPress Plugin", to: "/docs/wordpress/overview" },
						{ label: "CLI", to: "/docs/cli/overview" },
					],
				},
				{
					title: "Community",
					items: [
						{
							label: "GitHub",
							href: "https://codeberg.org/RugMunchMedia/walletpress",
						},
						{
							label: "Telegram",
							href: "https://t.me/walletpress",
						},
					],
				},
				{
					title: "More",
					items: [
						{ label: "Blog", to: "/blog" },
						{ label: "Changelog", to: "/docs/changelog" },
						{ label: "Security", to: "/docs/security/overview" },
					],
				},
			],
			copyright: "Copyright © 2026 Rug Munch Media LLC. Built with Docusaurus.",
		},
		prism: {
			theme: {
				plain: { color: "#393A34", backgroundColor: "#f6f8fa" },
				styles: [],
			},
			additionalLanguages: [
				"bash",
				"json",
				"yaml",
				"toml",
				"python",
				"solidity",
			],
		},
	},
	presets: [
		[
			"classic",
			{
				docs: {
					sidebarPath: require.resolve("./sidebars.js"),
					editUrl:
						"https://codeberg.org/RugMunchMedia/walletpress/tree/main/docs/",
				},
				blog: { showReadingTime: true },
				theme: { customCss: require.resolve("./src/css/custom.css") },
			},
		],
	],
};
