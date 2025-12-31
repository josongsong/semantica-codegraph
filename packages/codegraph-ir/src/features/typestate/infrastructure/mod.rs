/*
 * Typestate Infrastructure
 *
 * Built-in protocol definitions and parsers.
 */

mod built_in;
mod protocol_parser;

pub use built_in::{ConnectionProtocol, FileProtocol, LockProtocol};
pub use protocol_parser::{
    ParseError, PreconditionConfig, ProtocolBuilder, ProtocolConfig, ProtocolParser,
    TransitionConfig,
};
