// Index Builder - SOTA Parallel Index Construction
//
// Builds all graph indexes in parallel with SIMD optimizations where applicable

use ahash::{AHashMap, AHashSet};
use rayon::prelude::*;
use tracing::debug;

use super::builder::{intern_str, GraphBuilderError};
use crate::features::graph_builder::domain::{
    GraphEdge, GraphIndex, GraphNode, InternedString, RequestFlow,
};
use crate::shared::models::{EdgeKind, NodeKind};

pub struct IndexBuilder;

impl IndexBuilder {
    pub fn new() -> Self {
        Self
    }

    /// Build all graph indexes (PARALLEL)
    ///
    /// Builds 10+ index types in parallel using Rayon:
    /// - Reverse indexes (called_by, imported_by, etc.)
    /// - Adjacency indexes (outgoing, incoming)
    /// - EdgeKind-specific indexes
    /// - Extended indexes (routes, services, request flow)
    pub fn build_indexes(
        &self,
        nodes: &AHashMap<InternedString, GraphNode>,
        edges: &[GraphEdge],
    ) -> Result<GraphIndex, GraphBuilderError> {
        // Build all indexes in parallel using rayon::join
        // Build indexes in parallel (rayon::join only takes 2 closures)
        let (
            ((called_by, imported_by, contains_children), (type_users, reads_by, writes_by)),
            ((outgoing, incoming), (outgoing_by_kind, incoming_by_kind)),
        ) = rayon::join(
            || {
                rayon::join(
                    || self.build_reverse_indexes(edges),
                    || self.build_data_flow_indexes(edges),
                )
            },
            || {
                rayon::join(
                    || self.build_adjacency_indexes(edges),
                    || self.build_kind_specific_indexes(edges),
                )
            },
        );

        // Build extended indexes (sequential, as they depend on kind-specific indexes)
        let decorators_by_target = self.build_decorators_index(edges);
        let routes_by_path = self.build_routes_by_path_index(nodes);
        let services_by_domain = self.build_services_by_domain_index(nodes);
        let request_flow_index = self.build_request_flow_index(nodes, &outgoing_by_kind);

        Ok(GraphIndex {
            called_by,
            imported_by,
            contains_children,
            type_users,
            reads_by,
            writes_by,
            outgoing,
            incoming,
            outgoing_by_kind,
            incoming_by_kind,
            routes_by_path,
            services_by_domain,
            request_flow_index,
            decorators_by_target,
        })
    }

    /// Build path index for O(1) node lookup by file path (PARALLEL)
    pub fn build_path_index(
        &self,
        nodes: &AHashMap<InternedString, GraphNode>,
    ) -> Result<AHashMap<InternedString, AHashSet<InternedString>>, GraphBuilderError> {
        let path_index: AHashMap<InternedString, AHashSet<InternedString>> = nodes
            .par_iter()
            .filter_map(|(node_id, node)| {
                node.path
                    .as_ref()
                    .map(|path| (path.clone(), node_id.clone()))
            })
            .fold(AHashMap::new, |mut map, (path, node_id)| {
                map.entry(path)
                    .or_insert_with(AHashSet::new)
                    .insert(node_id);
                map
            })
            .reduce(AHashMap::new, |mut a, b| {
                for (path, node_ids) in b {
                    a.entry(path).or_insert_with(AHashSet::new).extend(node_ids);
                }
                a
            });

        Ok(path_index)
    }

    /// Build reverse indexes (PARALLEL)
    fn build_reverse_indexes(
        &self,
        edges: &[GraphEdge],
    ) -> (
        AHashMap<InternedString, Vec<InternedString>>,
        AHashMap<InternedString, Vec<InternedString>>,
        AHashMap<InternedString, Vec<InternedString>>,
    ) {
        let (called_by, (imported_by, contains_children)) = rayon::join(
            || self.build_index_for_kind(edges, EdgeKind::Calls),
            || {
                rayon::join(
                    || self.build_index_for_kind(edges, EdgeKind::Imports),
                    || self.build_index_for_kind_reverse(edges, EdgeKind::Contains),
                )
            },
        );

        (called_by, imported_by, contains_children)
    }

    /// Build data flow indexes (PARALLEL)
    fn build_data_flow_indexes(
        &self,
        edges: &[GraphEdge],
    ) -> (
        AHashMap<InternedString, Vec<InternedString>>,
        AHashMap<InternedString, Vec<InternedString>>,
        AHashMap<InternedString, Vec<InternedString>>,
    ) {
        let (type_users, (reads_by, writes_by)) = rayon::join(
            || self.build_index_for_kind(edges, EdgeKind::ReferencesType),
            || {
                rayon::join(
                    || self.build_index_for_kind(edges, EdgeKind::Reads),
                    || self.build_index_for_kind(edges, EdgeKind::Writes),
                )
            },
        );

        (type_users, reads_by, writes_by)
    }

    /// Build adjacency indexes (PARALLEL)
    fn build_adjacency_indexes(
        &self,
        edges: &[GraphEdge],
    ) -> (
        AHashMap<InternedString, Vec<InternedString>>,
        AHashMap<InternedString, Vec<InternedString>>,
    ) {
        rayon::join(
            || {
                // Outgoing: source → edge_ids
                edges
                    .par_iter()
                    .fold(AHashMap::new, |mut map, edge| {
                        map.entry(edge.source_id.clone())
                            .or_insert_with(Vec::new)
                            .push(edge.id.clone());
                        map
                    })
                    .reduce(AHashMap::new, |mut a, b| {
                        for (k, v) in b {
                            a.entry(k).or_insert_with(Vec::new).extend(v);
                        }
                        a
                    })
            },
            || {
                // Incoming: target → edge_ids
                edges
                    .par_iter()
                    .fold(AHashMap::new, |mut map, edge| {
                        map.entry(edge.target_id.clone())
                            .or_insert_with(Vec::new)
                            .push(edge.id.clone());
                        map
                    })
                    .reduce(AHashMap::new, |mut a, b| {
                        for (k, v) in b {
                            a.entry(k).or_insert_with(Vec::new).extend(v);
                        }
                        a
                    })
            },
        )
    }

    /// Build EdgeKind-specific indexes (PARALLEL)
    fn build_kind_specific_indexes(
        &self,
        edges: &[GraphEdge],
    ) -> (
        AHashMap<(InternedString, EdgeKind), Vec<InternedString>>,
        AHashMap<(InternedString, EdgeKind), Vec<InternedString>>,
    ) {
        rayon::join(
            || {
                // Outgoing by kind: (source, kind) → target_ids
                edges
                    .par_iter()
                    .fold(AHashMap::new, |mut map, edge| {
                        map.entry((edge.source_id.clone(), edge.kind))
                            .or_insert_with(Vec::new)
                            .push(edge.target_id.clone());
                        map
                    })
                    .reduce(AHashMap::new, |mut a, b| {
                        for (k, v) in b {
                            a.entry(k).or_insert_with(Vec::new).extend(v);
                        }
                        a
                    })
            },
            || {
                // Incoming by kind: (target, kind) → source_ids
                edges
                    .par_iter()
                    .fold(AHashMap::new, |mut map, edge| {
                        map.entry((edge.target_id.clone(), edge.kind))
                            .or_insert_with(Vec::new)
                            .push(edge.source_id.clone());
                        map
                    })
                    .reduce(AHashMap::new, |mut a, b| {
                        for (k, v) in b {
                            a.entry(k).or_insert_with(Vec::new).extend(v);
                        }
                        a
                    })
            },
        )
    }

    /// Build index for specific edge kind (target → sources)
    fn build_index_for_kind(
        &self,
        edges: &[GraphEdge],
        kind: EdgeKind,
    ) -> AHashMap<InternedString, Vec<InternedString>> {
        edges
            .par_iter()
            .filter(|e| e.kind == kind)
            .fold(AHashMap::new, |mut map, edge| {
                map.entry(edge.target_id.clone())
                    .or_insert_with(Vec::new)
                    .push(edge.source_id.clone());
                map
            })
            .reduce(AHashMap::new, |mut a, b| {
                for (k, v) in b {
                    a.entry(k).or_insert_with(Vec::new).extend(v);
                }
                a
            })
    }

    /// Build index for specific edge kind (source → targets) - for CONTAINS
    fn build_index_for_kind_reverse(
        &self,
        edges: &[GraphEdge],
        kind: EdgeKind,
    ) -> AHashMap<InternedString, Vec<InternedString>> {
        edges
            .par_iter()
            .filter(|e| e.kind == kind)
            .fold(AHashMap::new, |mut map, edge| {
                map.entry(edge.source_id.clone())
                    .or_insert_with(Vec::new)
                    .push(edge.target_id.clone());
                map
            })
            .reduce(AHashMap::new, |mut a, b| {
                for (k, v) in b {
                    a.entry(k).or_insert_with(Vec::new).extend(v);
                }
                a
            })
    }

    /// Build decorators index
    fn build_decorators_index(
        &self,
        edges: &[GraphEdge],
    ) -> AHashMap<InternedString, Vec<InternedString>> {
        self.build_index_for_kind(edges, EdgeKind::Decorates)
    }

    /// Build routes by path index
    fn build_routes_by_path_index(
        &self,
        nodes: &AHashMap<InternedString, GraphNode>,
    ) -> AHashMap<InternedString, Vec<InternedString>> {
        nodes
            .par_iter()
            .filter(|(_, node)| node.kind == NodeKind::Route)
            .filter_map(|(node_id, node)| {
                node.attrs
                    .get("route_path")
                    .or_else(|| node.attrs.get("path"))
                    .and_then(|v| v.as_str())
                    .map(|path| (intern_str(path), node_id.clone()))
            })
            .fold(AHashMap::new, |mut map, (path, node_id)| {
                map.entry(path).or_insert_with(Vec::new).push(node_id);
                map
            })
            .reduce(AHashMap::new, |mut a, b| {
                for (k, v) in b {
                    a.entry(k).or_insert_with(Vec::new).extend(v);
                }
                a
            })
    }

    /// Build services by domain index
    fn build_services_by_domain_index(
        &self,
        nodes: &AHashMap<InternedString, GraphNode>,
    ) -> AHashMap<InternedString, Vec<InternedString>> {
        nodes
            .par_iter()
            .filter(|(_, node)| node.kind == NodeKind::Service)
            .flat_map(|(node_id, node)| {
                let domains: Vec<String> = node
                    .attrs
                    .get("domain_tags")
                    .and_then(|v| {
                        if let Some(arr) = v.as_array() {
                            Some(
                                arr.iter()
                                    .filter_map(|v| v.as_str().map(String::from))
                                    .collect(),
                            )
                        } else if let Some(s) = v.as_str() {
                            Some(vec![s.to_string()])
                        } else {
                            None
                        }
                    })
                    .unwrap_or_default();

                domains
                    .into_iter()
                    .map(move |domain| (intern_str(&domain), node_id.clone()))
                    .collect::<Vec<_>>()
            })
            .fold(AHashMap::new, |mut map, (domain, node_id)| {
                map.entry(domain).or_insert_with(Vec::new).push(node_id);
                map
            })
            .reduce(AHashMap::new, |mut a, b| {
                for (k, v) in b {
                    a.entry(k).or_insert_with(Vec::new).extend(v);
                }
                a
            })
    }

    /// Build request flow index (Route → Handler → Service → Repository)
    fn build_request_flow_index(
        &self,
        nodes: &AHashMap<InternedString, GraphNode>,
        outgoing_by_kind: &AHashMap<(InternedString, EdgeKind), Vec<InternedString>>,
    ) -> AHashMap<InternedString, RequestFlow> {
        use std::collections::HashMap;

        let flows: HashMap<InternedString, RequestFlow> = nodes
            .par_iter()
            .filter(|(_, node)| node.kind == NodeKind::Route)
            .map(|(route_id, _)| {
                let flow = self.trace_route_flow(route_id, outgoing_by_kind);
                (route_id.clone(), flow)
            })
            .collect();

        // Convert HashMap to AHashMap
        flows.into_iter().collect()
    }

    /// Trace route flow using edge indexes
    fn trace_route_flow(
        &self,
        route_id: &InternedString,
        outgoing_by_kind: &AHashMap<(InternedString, EdgeKind), Vec<InternedString>>,
    ) -> RequestFlow {
        let mut flow = RequestFlow::default();

        // Find handlers
        if let Some(handlers) = outgoing_by_kind.get(&(route_id.clone(), EdgeKind::RouteHandler)) {
            flow.handlers = handlers.clone();

            // Find services from handlers
            let mut services = Vec::new();
            for handler_id in handlers {
                if let Some(handler_services) =
                    outgoing_by_kind.get(&(handler_id.clone(), EdgeKind::HandlesRequest))
                {
                    services.extend(handler_services.clone());
                }
            }
            flow.services = services;

            // Find repositories from services
            let mut repositories = Vec::new();
            for service_id in &flow.services {
                if let Some(repos) =
                    outgoing_by_kind.get(&(service_id.clone(), EdgeKind::UsesRepository))
                {
                    repositories.extend(repos.clone());
                }
            }
            flow.repositories = repositories;
        }

        flow
    }
}

impl Default for IndexBuilder {
    fn default() -> Self {
        Self::new()
    }
}
