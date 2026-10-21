import React, { useEffect, useRef, useState } from "react";
import {
  motion,
  useScroll,
  useTransform,
  useSpring,
  useInView,
} from "framer-motion";
import {
  Menu,
  X,
  ArrowDown,
  ArrowUpRight,
  MapPin,
  Waves,
  Fingerprint,
  ScanEye,
  Activity,
} from "lucide-react";
import oceanSurface from "./assets/ocean-surface.jpg";
import sailboat from "./assets/sailboat.png";
import underwater from "./assets/underwater.jpg";
import "./styles.css";

/*
  AQUA LENS — OCEAN EXPEDITION

  The imagery is replaceable.
  For the closest match to the reference, use a
  custom split-level ocean photograph for the hero.
*/

const ASSETS = {
  sky: oceanSurface,
  boat: sailboat,
  underwater: underwater,

  sample:
    "https://images.unsplash.com/photo-1518837695005-2083093ee35b?w=1000&q=85",

  analysis:
    "https://images.unsplash.com/photo-1546026423-cc4642628d2b?w=1000&q=85",

  reef:
    "https://images.unsplash.com/photo-1544551763-46a013bb70d5?w=1000&q=85",
};
const stops = [
  {
    id: "01",
    title: "THE OBSERVATION",
    eyebrow: "01 / IMAGE ACQUISITION",
    image: ASSETS.sample,
    description:
      "Every investigation begins with observation. AquaLens examines water imagery to identify visible characteristics that may reveal changes in a sample's condition.",
    detail: "CAPTURE · PREPROCESS · OBSERVE",
  },
  {
    id: "02",
    title: "THE VISUAL LANGUAGE",
    eyebrow: "02 / FEATURE EXTRACTION",
    image: ASSETS.analysis,
    description:
      "Colour, texture, intensity and structural information are converted into numerical descriptors. Our feature-selection process reduces an initial set of 99 features to 20 candidate descriptors.",
    detail: "99 FEATURES → 20 DESCRIPTORS",
  },
  {
    id: "03",
    title: "THE INTELLIGENCE",
    eyebrow: "03 / MACHINE LEARNING",
    image: ASSETS.reef,
    description:
      "A Random Forest classifier interprets the extracted visual features to distinguish between three labelled water-image condition categories.",
    detail: "RANDOM FOREST · 83.38% TEST ACCURACY",
  },
];

function FadeIn({ children, className = "", delay = 0 }) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 55 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.2 }}
      transition={{
        duration: 0.95,
        delay,
        ease: [0.22, 1, 0.36, 1],
      }}
    >
      {children}
    </motion.div>
  );
}

/* ---------------- NAVIGATION ---------------- */

function Navigation() {
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 100);
    onScroll();

    window.addEventListener("scroll", onScroll, {
      passive: true,
    });

    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <>
      <header className={`navigation ${scrolled ? "is-scrolled" : ""}`}>
        <a href="#surface" className="logo">
          <Waves size={23} strokeWidth={1.6} />
          <span>AquaLens</span>
          <small>AI</small>
        </a>

        <nav className="desktop-navigation">
          <a href="#surface">Surface</a>
          <a href="#mission">The Mission</a>
          <a href="#expedition">Expedition</a>
          <a href="#deep">The Deep</a>
        </nav>

        <a href="/login" className="navigation-action">
          EXPLORE PLATFORM <ArrowUpRight size={15} />
        </a>

        <button
          className="menu-toggle"
          onClick={() => setOpen(!open)}
          aria-label="Toggle navigation"
          aria-expanded={open}
        >
          {open ? <X size={24} /> : <Menu size={24} />}
        </button>
      </header>

      {open && (
        <motion.div
          className="mobile-navigation"
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
        >
          {[
            ["Surface", "#surface"],
            ["The Mission", "#mission"],
            ["Expedition", "#expedition"],
            ["The Deep", "#deep"],
            ["Explore Platform", "/login"],
          ].map(([label, href]) => (
            <a key={href} href={href} onClick={() => setOpen(false)}>
              {label}
            </a>
          ))}
        </motion.div>
      )}
    </>
  );
}

/* ---------------- WATER SURFACE ---------------- */

function OceanHero() {
  const heroRef = useRef(null);

  const { scrollYProgress } = useScroll({
    target: heroRef,
    offset: ["start start", "end start"],
  });

  const smoothProgress = useSpring(scrollYProgress, {
    stiffness: 55,
    damping: 25,
    mass: 0.8,
  });

  const skyY = useTransform(smoothProgress, [0, 1], ["0%", "18%"]);
  const boatY = useTransform(smoothProgress, [0, 1], ["0%", "25%"]);
  const waterY = useTransform(smoothProgress, [0, 1], ["0%", "-8%"]);

  const textY = useTransform(smoothProgress, [0, 0.8], [0, -110]);
  const textOpacity = useTransform(
    smoothProgress,
    [0, 0.55, 0.85],
    [1, 1, 0]
  );

  const waterOpacity = useTransform(
    smoothProgress,
    [0, 0.6, 1],
    [0.8, 0.95, 1]
  );

  return (
    <section className="ocean-hero" id="surface" ref={heroRef}>
      {/* Sky and ocean background */}
      <motion.div
        className="sky-layer"
        style={{
          backgroundImage: `url(${ASSETS.sky})`,
          y: skyY,
        }}
      />

      <div className="sky-wash" />

      {/* Boat */}
      <motion.img
        className="hero-boat"
        src={ASSETS.boat}
        alt="Sailboat exploring the ocean"
        style={{ y: boatY }}
      />

      {/* Underwater layer */}
      <motion.div
        className="ocean-surface-layer"
        style={{
          y: waterY,
          opacity: waterOpacity,
        }}
      >
        <div
          className="underwater-photo"
          style={{
            backgroundImage: `url(${ASSETS.underwater})`,
          }}
        />

        <div className="water-surface-line" />
      </motion.div>

      <div className="underwater-light" />

      {/* Hero text */}
      <motion.div
        className="hero-copy"
        style={{
          y: textY,
          opacity: textOpacity,
        }}
      >
        <motion.span
          className="hero-overline"
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8 }}
        >
          AN EXPEDITION INTO WATER INTELLIGENCE
        </motion.span>

        <motion.h1
          initial={{ opacity: 0, y: 35 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{
            duration: 1.1,
            delay: 0.15,
            ease: [0.22, 1, 0.36, 1],
          }}
        >
          BEYOND
          <br />
          THE SURFACE<span>.</span>
        </motion.h1>

        <div className="hero-description">
          <p>
            AQUALENS AI
            <br />
            Water Fingerprinting & Intelligent
            <br />
            Quality Monitoring
          </p>

          <div className="hero-coordinate">
            <span>RESEARCH EXPEDITION</span>
            <span>2026</span>
            <span>VISUAL WATER INTELLIGENCE</span>
          </div>
        </div>

        <motion.a
          className="orange-button"
          href="#mission"
          whileHover={{ y: -3 }}
          whileTap={{ scale: 0.97 }}
        >
          BEGIN THE DIVE <ArrowDown size={17} />
        </motion.a>
      </motion.div>

      <div className="hero-bottom-label">
        <span>01 / THE SURFACE</span>
        <span>SCROLL TO DESCEND ↓</span>
      </div>

      <div className="hero-to-mission-blend" />
    </section>
  );
}
/* ---------------- DEPTH INDICATOR ---------------- */

function DepthIndicator() {
  const { scrollYProgress } = useScroll();

  const progress = useSpring(scrollYProgress, {
    stiffness: 90,
    damping: 25,
  });

  const depth = useTransform(progress, [0, 1], [0, 100]);

  const [percentage, setPercentage] = useState(0);

  useEffect(() => {
    return depth.on("change", (value) => {
      setPercentage(Math.round(value));
    });
  }, [depth]);

  return (
    <div className="depth-indicator">
      <span>DESCENT</span>

      <div className="depth-track">
        <motion.div
          className="depth-progress"
          style={{ scaleY: progress }}
        />
      </div>

      <strong>{String(percentage).padStart(2, "0")}%</strong>
    </div>
  );
}

/* ---------------- TRANSITION ---------------- */

function Mission() {
  return (
    <section className="mission-section" id="mission">
      <div className="mission-rays" />

      <div className="mission-inner">
        <FadeIn>
          <div className="chapter-label">
            <span>CHAPTER I</span>
            <span className="chapter-line" />
            THE DESCENT
          </div>
        </FadeIn>

        <div className="mission-grid">
          <FadeIn>
            <h2>
              THERE IS MORE
              <br />
              TO WATER THAN
              <br />
              <em>WE CAN SEE.</em>
            </h2>
          </FadeIn>

          <FadeIn delay={0.2}>
            <div className="mission-copy">
              <span className="small-marker">THE QUESTION</span>

              <p>
                Can the visual characteristics of water tell us
                something meaningful about its changing condition?
              </p>

              <p>
                AquaLens AI investigates this question through
                computer vision, machine learning, and the
                development of a compact visual representation.
              </p>

              <a href="#expedition" className="underlined-link">
                FOLLOW THE INVESTIGATION
                <ArrowDown size={16} />
              </a>
            </div>
          </FadeIn>
        </div>
      </div>
    </section>
  );
}

/* ---------------- EXPEDITION PATH ---------------- */

function ExpeditionStop({ stop, index }) {
  return (
    <article
      className={`expedition-stop ${
        index % 2 === 1 ? "stop-reversed" : ""
      }`}
    >
      <FadeIn className="stop-image-container">
        <motion.div
          className="stop-image-frame"
          whileHover={{ scale: 1.025 }}
          transition={{ duration: 0.6 }}
        >
          <img src={stop.image} alt={stop.title} />

          <div className="stop-image-shade" />

          <div className="stop-image-caption">
            <span>{stop.detail}</span>
            <ArrowUpRight size={16} />
          </div>
        </motion.div>

        <div className="stop-pin">
          <MapPin size={22} />
        </div>
      </FadeIn>

      <FadeIn className="stop-copy" delay={0.15}>
        <span className="stop-eyebrow">{stop.eyebrow}</span>

        <h3>{stop.title}</h3>

        <p>{stop.description}</p>

        <div className="stop-separator" />
        <span className="stop-number">STATION {stop.id}</span>
      </FadeIn>
    </article>
  );
}

function Expedition() {
  const pathRef = useRef(null);

  const { scrollYProgress } = useScroll({
    target: pathRef,
    offset: ["start 75%", "end 70%"],
  });

  const pathLength = useSpring(scrollYProgress, {
    stiffness: 70,
    damping: 25,
  });

  return (
    <section className="expedition-section" id="expedition">
      <div className="expedition-inner">
        <FadeIn>
          <div className="chapter-label">
            <span>CHAPTER II</span>
            <span className="chapter-line" />
            THE INVESTIGATION
          </div>

          <h2 className="expedition-heading">
            FOLLOW THE
            <br />
            <em>UNSEEN.</em>
          </h2>

          <p className="expedition-intro">
            Three stages. One investigation.
            From what the camera captures to what
            the model learns.
          </p>
        </FadeIn>

        <div className="expedition-route" ref={pathRef}>
          <svg
            className="route-svg"
            viewBox="0 0 1000 1800"
            preserveAspectRatio="none"
            aria-hidden="true"
          >
            <path
              d="
                M 720 80
                C 710 250, 250 230, 250 460
                C 250 650, 760 610, 760 890
                C 760 1120, 260 1060, 260 1330
                C 260 1560, 730 1490, 730 1740
              "
              fill="none"
              stroke="rgba(207,225,235,.18)"
              strokeWidth="2"
              strokeDasharray="8 12"
            />

            <motion.path
              d="
                M 720 80
                C 710 250, 250 230, 250 460
                C 250 650, 760 610, 760 890
                C 760 1120, 260 1060, 260 1330
                C 260 1560, 730 1490, 730 1740
              "
              fill="none"
              stroke="#da8c60"
              strokeWidth="2.5"
              strokeDasharray="8 12"
              style={{ pathLength }}
            />
          </svg>

          {stops.map((stop, index) => (
            <ExpeditionStop
              key={stop.id}
              stop={stop}
              index={index}
            />
          ))}
        </div>
      </div>
    </section>
  );
}

/* ---------------- THE DEEP ---------------- */

function DeepSection() {
  const sectionRef = useRef(null);

  const { scrollYProgress } = useScroll({
    target: sectionRef,
    offset: ["start end", "end start"],
  });

  const glowY = useTransform(
    scrollYProgress,
    [0, 1],
    [100, -100]
  );

  return (
    <section className="deep-section" id="deep" ref={sectionRef}>
      <motion.div className="deep-glow" style={{ y: glowY }} />

      <div className="deep-content">
        <FadeIn>
          <div className="chapter-label centered">
            <span>CHAPTER III</span>
            <span className="chapter-line" />
            THE DISCOVERY
          </div>

          <span className="deep-symbol">
            <Fingerprint size={62} strokeWidth={0.8} />
          </span>

          <h2>
            EVERY WATER
            <br />
            SOURCE HAS
            <br />
            <em>A STORY.</em>
          </h2>

          <p>
            Our next research direction is the Water Fingerprint:
            a source-specific visual baseline that could help
            distinguish expected variation from unusual changes
            over time.
          </p>

          <span className="concept-label">
            PROPOSED RESEARCH STAGE · NOT YET VALIDATED
          </span>
        </FadeIn>
      </div>
    </section>
  );
}

/* ---------------- PROJECT FACTS ---------------- */

function ResearchFacts() {
  return (
    <section className="research-facts">
      <div className="facts-grid">
        {[
          ["6,515", "IMAGES IN O2 DATASET"],
          ["20", "VISUAL FEATURES"],
          ["83.38%", "RF TEST ACCURACY"],
          ["0.5996", "RF MACRO-F1"],
        ].map(([value, label]) => (
          <FadeIn key={label}>
            <div className="fact">
              <strong>{value}</strong>
              <span>{label}</span>
            </div>
          </FadeIn>
        ))}
      </div>

      <p>
        These figures describe the image-based classification
        experiment, not chemical water safety or potability.
      </p>
    </section>
  );
}

/* ---------------- ENDING ---------------- */

function Ending() {
  return (
    <section className="ending-section">
      <FadeIn>
        <span className="ending-eyebrow">
          THE EXPEDITION DOES NOT END HERE
        </span>

        <h2>
          THERE IS STILL
          <br />
          MORE TO <em>DISCOVER.</em>
        </h2>

        <p>
          From visual classification to future
          source-specific water monitoring.
        </p>

        <a href="#surface" className="orange-button">
          RETURN TO THE SURFACE
          <ArrowUpRight size={17} />
        </a>
      </FadeIn>
    </section>
  );
}

/* ---------------- FOOTER ---------------- */

function Footer() {
  return (
    <footer className="site-footer">
      <div className="footer-top">
        <div>
          <div className="footer-logo">
            <Waves size={28} />
            AquaLens AI
          </div>

          <p>
            Water Fingerprinting &
            <br />
            Intelligent Quality Monitoring
          </p>
        </div>

        <div className="footer-navigation">
          <a href="#surface">Surface</a>
          <a href="#mission">Mission</a>
          <a href="#expedition">Expedition</a>
          <a href="#deep">Research</a>
        </div>
      </div>

      <div className="footer-bottom">
        <span>© 2026 AQUALENS AI</span>
        <span>AN EXPLORATION OF WATER INTELLIGENCE</span>
        <a href="#surface">BACK TO TOP ↑</a>
      </div>
    </footer>
  );
}

export default function LandingPage() {
  return (
    <div className="aqualens-app">
      <Navigation />
      <DepthIndicator />

      <OceanHero />
      <Mission />
      <Expedition />
      <ResearchFacts />
      <DeepSection />
      <Ending />
      <Footer />
    </div>
  );
}