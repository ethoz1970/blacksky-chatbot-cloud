# Engineering Standards & Technical Ethos

**Metadata**
- **Category:** Engineering / Development Standards
- **Target Audience:** Internal Developers, Freelancers, Technical Stakeholders
- **Key Themes:** Drupal 10, Redis, Python, Librosa, MicroPython, Raspberry Pi Pico, Azure, Lando

## Core Statement
Our engineering philosophy is built on the pillars of **Stability, Transparency, and Precision.** We build modular systems that are easy to debug and document, ensuring that our technical debt remains low while our innovation speed remains high.

## Key Principles & Values
* **Local-First Development:** We use **Lando** on macOS to mirror production environments. This ensures consistency from the first line of code to the final deployment.
* **Resilient Infrastructure:** For production environments on **Azure**, we utilize **Redis clusters** to handle high-concurrency loads. We prioritize "MOVED" error handling and cluster-aware client configurations to maintain 100% uptime.
* **Readable Audio Logic:** When using **Python and Librosa** for audio analysis, we prioritize mathematical clarity. Every digital signal processing (DSP) script must include comments explaining the sampling rate and feature extraction choices (e.g., MFCCs or Mel-spectrograms).
* **Hardware Efficiency:** For **MicroPython** development on the **Raspberry Pi Pico W**, we write memory-efficient code, utilizing interrupts and asyncio to keep the hardware responsive while maintaining a low power footprint.

## Coding Practices
1. **Drupal Best Practices:** Always use the Drupal 10 Plugin API for custom modules. Hard-coded logic is prohibited.
2. **Version Control:** Every Pull Request (PR) must be linked to a specific project task. We use descriptive commit messages that explain "Why" a change was made, not just "What."
3. **Environment Parity:** No developer should ever "fix" a bug directly in the Azure portal; all changes must flow from Lando through our CI/CD pipeline.

## Frequently Asked Questions (Q&A)
**Q: Why do we use Redis clusters instead of a single instance?**
**A:** We use Redis clusters to ensure high availability and scalability for our Drupal 10 applications, preventing single points of failure during traffic spikes.

**Q: What is our standard for audio analysis libraries?**
**A:** We standardize on **Librosa** for Python due to its robust community support and precision in handling time-series audio data.

**Q: How do we handle MicroPython deployment on the Pico?**
**A:** We utilize a modular approach, separating hardware-specific drivers from core logic to ensure the code can be easily tested and updated.