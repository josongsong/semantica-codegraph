//! Context Provider Infrastructure - Concrete implementations
//!
//! Provides concrete context provider adapters:
//! - Static context (for testing and simple use cases)
//! - Registry for multi-provider fusion
//!
//! Production adapters (IDE, Git, History) would be implemented in application layer.

use crate::features::repomap::domain::context::{
    ContextItem, ContextProvider, ContextSet, ContextType,
};
use std::sync::Arc;

/// Static context provider (for testing and simple cases)
///
/// Returns a pre-defined set of context items.
pub struct StaticContextProvider {
    name: String,
    context_type: ContextType,
    items: Vec<ContextItem>,
}

impl StaticContextProvider {
    /// Create new static provider
    pub fn new(name: String, context_type: ContextType, items: Vec<ContextItem>) -> Self {
        Self {
            name,
            context_type,
            items,
        }
    }
}

impl ContextProvider for StaticContextProvider {
    fn get_context(&self) -> Result<Vec<ContextItem>, String> {
        Ok(self.items.clone())
    }

    fn context_type(&self) -> ContextType {
        self.context_type
    }

    fn name(&self) -> &str {
        &self.name
    }
}

/// Context Provider Registry
///
/// Aggregates context from multiple providers and fuses them into a single ContextSet.
/// Uses weighted fusion based on ContextSet type_weights.
pub struct ContextProviderRegistry {
    providers: Vec<Arc<dyn ContextProvider>>,
}

impl ContextProviderRegistry {
    /// Create new registry
    pub fn new() -> Self {
        Self {
            providers: Vec::new(),
        }
    }

    /// Register a provider
    pub fn register(&mut self, provider: Arc<dyn ContextProvider>) {
        self.providers.push(provider);
    }

    /// Get fused context from all providers
    ///
    /// Collects context from all registered providers and combines them
    /// into a single ContextSet.
    pub fn get_fused_context(&self) -> Result<ContextSet, Vec<String>> {
        let mut context_set = ContextSet::new();
        let mut errors = Vec::new();

        for provider in &self.providers {
            match provider.get_context() {
                Ok(items) => {
                    for item in items {
                        context_set.add_item(item);
                    }
                }
                Err(e) => {
                    errors.push(format!("Provider '{}' failed: {}", provider.name(), e));
                }
            }
        }

        if !errors.is_empty() && context_set.items.is_empty() {
            // All providers failed
            return Err(errors);
        }

        Ok(context_set)
    }

    /// Get context with custom type weights
    pub fn get_fused_context_with_weights(
        &self,
        type_weights: std::collections::HashMap<ContextType, f64>,
    ) -> Result<ContextSet, Vec<String>> {
        let mut context_set = self.get_fused_context()?;
        context_set.type_weights = type_weights;
        Ok(context_set)
    }

    /// Number of registered providers
    pub fn provider_count(&self) -> usize {
        self.providers.len()
    }
}

impl Default for ContextProviderRegistry {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_static_provider() {
        let items = vec![
            ContextItem::new("node1".to_string(), ContextType::Ide, 0.8),
            ContextItem::new("node2".to_string(), ContextType::Ide, 0.6),
        ];

        let provider = StaticContextProvider::new(
            "test_provider".to_string(),
            ContextType::Ide,
            items.clone(),
        );

        assert_eq!(provider.name(), "test_provider");
        assert_eq!(provider.context_type(), ContextType::Ide);

        let result = provider.get_context().unwrap();
        assert_eq!(result.len(), 2);
        assert_eq!(result[0].node_id, "node1");
        assert_eq!(result[1].node_id, "node2");
    }

    #[test]
    fn test_registry_empty() {
        let registry = ContextProviderRegistry::new();
        assert_eq!(registry.provider_count(), 0);

        let context = registry.get_fused_context().unwrap();
        assert_eq!(context.items.len(), 0);
    }

    #[test]
    fn test_registry_single_provider() {
        let mut registry = ContextProviderRegistry::new();

        let items = vec![ContextItem::new("node1".to_string(), ContextType::Ide, 0.8)];
        let provider = Arc::new(StaticContextProvider::new(
            "ide".to_string(),
            ContextType::Ide,
            items,
        ));

        registry.register(provider);
        assert_eq!(registry.provider_count(), 1);

        let context = registry.get_fused_context().unwrap();
        assert_eq!(context.items.len(), 1);
        assert_eq!(context.items[0].node_id, "node1");
    }

    #[test]
    fn test_registry_multiple_providers() {
        let mut registry = ContextProviderRegistry::new();

        // IDE provider
        let ide_items = vec![
            ContextItem::new("node1".to_string(), ContextType::Ide, 0.8),
            ContextItem::new("node2".to_string(), ContextType::Ide, 0.6),
        ];
        let ide_provider = Arc::new(StaticContextProvider::new(
            "ide".to_string(),
            ContextType::Ide,
            ide_items,
        ));

        // Query provider
        let query_items = vec![ContextItem::new(
            "node3".to_string(),
            ContextType::Query,
            0.9,
        )];
        let query_provider = Arc::new(StaticContextProvider::new(
            "query".to_string(),
            ContextType::Query,
            query_items,
        ));

        registry.register(ide_provider);
        registry.register(query_provider);
        assert_eq!(registry.provider_count(), 2);

        let context = registry.get_fused_context().unwrap();
        assert_eq!(context.items.len(), 3);

        // Check all items are present
        let node_ids: Vec<String> = context
            .items
            .iter()
            .map(|item| item.node_id.clone())
            .collect();
        assert!(node_ids.contains(&"node1".to_string()));
        assert!(node_ids.contains(&"node2".to_string()));
        assert!(node_ids.contains(&"node3".to_string()));
    }

    #[test]
    fn test_registry_fused_context_with_weights() {
        let mut registry = ContextProviderRegistry::new();

        let items = vec![
            ContextItem::new("node1".to_string(), ContextType::Ide, 0.8),
            ContextItem::new("node2".to_string(), ContextType::Query, 0.6),
        ];
        let provider = Arc::new(StaticContextProvider::new(
            "test".to_string(),
            ContextType::Ide,
            items,
        ));

        registry.register(provider);

        // Custom weights
        let mut weights = std::collections::HashMap::new();
        weights.insert(ContextType::Ide, 0.7);
        weights.insert(ContextType::Query, 0.3);

        let context = registry.get_fused_context_with_weights(weights).unwrap();
        assert_eq!(context.type_weights.get(&ContextType::Ide), Some(&0.7));
        assert_eq!(context.type_weights.get(&ContextType::Query), Some(&0.3));
    }

    #[test]
    fn test_registry_provider_failure_handling() {
        // Test with failing provider
        struct FailingProvider;
        impl ContextProvider for FailingProvider {
            fn get_context(&self) -> Result<Vec<ContextItem>, String> {
                Err("Provider failed".to_string())
            }
            fn context_type(&self) -> ContextType {
                ContextType::Ide
            }
            fn name(&self) -> &str {
                "failing"
            }
        }

        let mut registry = ContextProviderRegistry::new();
        registry.register(Arc::new(FailingProvider));

        // Should return error since all providers failed
        let result = registry.get_fused_context();
        assert!(result.is_err());
        let errors = result.unwrap_err();
        assert_eq!(errors.len(), 1);
        assert!(errors[0].contains("failing"));
    }

    #[test]
    fn test_registry_partial_failure() {
        // Test with one failing and one succeeding provider
        struct FailingProvider;
        impl ContextProvider for FailingProvider {
            fn get_context(&self) -> Result<Vec<ContextItem>, String> {
                Err("Provider failed".to_string())
            }
            fn context_type(&self) -> ContextType {
                ContextType::Ide
            }
            fn name(&self) -> &str {
                "failing"
            }
        }

        let mut registry = ContextProviderRegistry::new();

        // Add failing provider
        registry.register(Arc::new(FailingProvider));

        // Add working provider
        let items = vec![ContextItem::new(
            "node1".to_string(),
            ContextType::Query,
            0.8,
        )];
        let working_provider = Arc::new(StaticContextProvider::new(
            "working".to_string(),
            ContextType::Query,
            items,
        ));
        registry.register(working_provider);

        // Should succeed with items from working provider
        let context = registry.get_fused_context().unwrap();
        assert_eq!(context.items.len(), 1);
        assert_eq!(context.items[0].node_id, "node1");
    }
}
