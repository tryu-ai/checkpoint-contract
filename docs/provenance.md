# Provenance and third-party notice

The checker, adapters, examples and tests are original project implementation.
Fixtures contain handcrafted synthetic occurrence IDs, not copied datasets,
model weights or private records. No third-party implementation is vendored.

The project uses the MIT license in [LICENSE](../LICENSE), with the standard
[SPDX MIT text](https://spdx.org/licenses/MIT.html) and copyright
2026 checkpoint-contract contributors.

Optional dependencies are separately licensed:

| Dependency | License reference |
| --- | --- |
| Hugging Face datasets | [Apache-2.0](https://github.com/huggingface/datasets/blob/main/LICENSE) |
| TorchData | [BSD-3-Clause](https://github.com/pytorch/data/blob/main/LICENSE) |

Installing optional stacks brings their own dependencies and license obligations;
this notice does not replace their distributions' notices. Naming frameworks,
referencing documentation or reproducing regression inputs does not imply
endorsement or affiliation. Historical cases are described in
[compatibility](compatibility.md); synthetic faulty Sessions are pedagogical
controls, not framework evidence.
