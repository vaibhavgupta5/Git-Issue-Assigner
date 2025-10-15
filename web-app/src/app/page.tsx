'use client';

import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Github, Zap, Brain, Users, ArrowRight, Check, Menu, X, Shield, BarChart, Sparkles } from 'lucide-react';

export default function LandingPage() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const features = [
    {
      icon: <Brain className="w-8 h-8" />,
      title: "AI-Powered Triage",
      description: "Intelligent bug classification using advanced machine learning and natural language processing"
    },
    {
      icon: <Users className="w-8 h-8" />,
      title: "Smart Assignment",
      description: "Automatically match bugs to the right developers based on expertise and availability"
    },
    {
      icon: <Zap className="w-8 h-8" />,
      title: "Real-Time Processing",
      description: "Instant bug analysis and assignment as soon as issues are created"
    },
    {
      icon: <BarChart className="w-8 h-8" />,
      title: "Performance Analytics",
      description: "Track team productivity and optimize your bug resolution workflow"
    },
    {
      icon: <Shield className="w-8 h-8" />,
      title: "Multi-Platform",
      description: "Seamless integration with GitHub, Jira, and your existing tools"
    },
    {
      icon: <Sparkles className="w-8 h-8" />,
      title: "Continuous Learning",
      description: "ML models that improve over time by learning from your team's patterns"
    }
  ];

  const team = [
    { name: "Satvik", role: "Lead Developer" },
    { name: "Vaibhav", role: "AI/ML Engineer" },
    { name: "Tulika", role: "Backend Developer" },
    { name: "Sumit", role: "Frontend Developer" },
    { name: "Varun", role: "DevOps Engineer" }
  ];

  const benefits = [
    "Reduce bug triage time by 80%",
    "94% assignment accuracy",
    "Automatic workload balancing",
    "Skill-based matching",
    "Real-time notifications",
    "Comprehensive analytics"
  ];

  return (
    <div className="min-h-screen bg-black text-white">
      {/* Navigation */}
      <nav className="border-b-4 border-r-4 border-white">
        <div className="max-w-7xl mx-auto px-6 lg:px-12">
          <div className="flex justify-between items-center h-20">
            <motion.div 
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              className="text-2xl font-bold"
            >
              Smart Bug Triage
            </motion.div>
            
            <div className="hidden md:flex items-center gap-8">
              <a href="#features" className="hover:opacity-60 transition-opacity">Features</a>
              <a href="#how-it-works" className="hover:opacity-60 transition-opacity">How It Works</a>
              <a href="#team" className="hover:opacity-60 transition-opacity">Team</a>
              <button className="bg-white text-black px-6 py-3 border-4 border-white hover:bg-black hover:text-white transition-colors font-semibold"
                onClick={() => {
                  window.open("/ai", "_blank");
                }}
              >
                Get Started
              </button>
            </div>

            <button 
              className="md:hidden text-white"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            >
              {mobileMenuOpen ? <X /> : <Menu />}
            </button>
          </div>
        </div>

        {mobileMenuOpen && (
          <motion.div 
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            className="md:hidden border-t-4 border-white bg-black"
          >
            <div className="px-6 py-4 space-y-4">
              <a href="#features" className="block py-2">Features</a>
              <a href="#how-it-works" className="block py-2">How It Works</a>
              <a href="#team" className="block py-2">Team</a>
              <button className="w-full bg-white text-black px-6 py-3 border-4 border-white font-semibold">
                Get Started
              </button>
            </div>
          </motion.div>
        )}
      </nav>

      {/* Hero Section */}
      <section className="border-b-4 border-r-4 border-white">
        <div className="max-w-7xl mx-auto px-6 lg:px-12 py-24 lg:py-12">
          <div className="grid lg:grid-cols-2 gap-16 items-center">
            <motion.div
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6 }}
            >
              <div className="inline-block border-4 border-white px-4 py-2 mb-6 text-sm font-bold">
                AI-POWERED BUG MANAGEMENT
              </div>
              <h1 className="text-5xl lg:text-7xl font-bold mb-6 leading-tight">
                Triage Bugs Intelligently, Assign Instantly
              </h1>
              <p className="text-xl lg:text-2xl mb-8 opacity-70">
                Let AI handle bug classification and developer assignment. Focus on what matters—building great software.
              </p>
              <div className="flex flex-col sm:flex-row gap-4">
                <button className="bg-white text-black px-8 py-4 border-4 border-white text-lg font-semibold hover:bg-black hover:text-white transition-colors flex items-center justify-center gap-2" onClick={() =>{
window.open("/ai", "_blank");
                }}>
                  Start Free Trial <ArrowRight className="w-5 h-5" />
                </button>
                <button className="bg-black text-white px-8 py-4 border-4 border-white text-lg font-semibold hover:bg-white hover:text-black transition-colors flex items-center justify-center gap-2">
                  <Github className="w-5 h-5" /> View Demo
                </button>
              </div>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.6, delay: 0.2 }}
              className="border-4 border-r-8 border-b-8 border-white p-8 bg-black"
            >
              <div className="space-y-4">
                <div className="border-4 border-white p-4 bg-white text-black">
                  <div className="text-xs font-bold mb-2 opacity-60">NEW ISSUE DETECTED</div>
                  <div className="font-semibold">Critical API Timeout in /auth endpoint</div>
                </div>
                <div className="border-4 border-white p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <Brain className="w-5 h-5" />
                    <span className="font-semibold">AI Analysis Complete</span>
                  </div>
                  <div className="text-sm space-y-1">
                    <div>Category: <span className="text-white">Backend API</span></div>
                    <div>Severity: <span className="text-white">Critical</span></div>
                    <div>Skills: <span className="text-white">Node.js, Redis</span></div>
                  </div>
                </div>
                <div className="border-4 border-white p-4 bg-white text-black">
                  <div className="flex items-center gap-2 mb-2">
                    <Check className="w-5 h-5" />
                    <span className="font-semibold">Assigned to Vaibhav</span>
                  </div>
                  <div className="text-sm opacity-60">Match score: 96% • Available now</div>
                </div>
              </div>
            </motion.div>
          </div>
        </div>
      </section>

      {/* Stats Section */}
      <section className="border-b-4 border-r-4 border-white">
        <div className="max-w-7xl mx-auto px-6 lg:px-12 py-16">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-8">
            {[
              { value: "80%", label: "Faster Triage" },
              { value: "96%", label: "Match Accuracy" },
              { value: "24/7", label: "Monitoring" },
              { value: "5ms", label: "Avg Response" }
            ].map((stat, idx) => (
              <motion.div
                key={idx}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: idx * 0.1 }}
                className="text-center border-4 border-r-8 border-b-8 border-white p-6"
              >
                <div className="text-4xl lg:text-5xl font-bold mb-2">{stat.value}</div>
                <div className="text-lg opacity-60">{stat.label}</div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section id="features" className="border-b-4 border-r-4 border-white">
        <div className="max-w-7xl mx-auto px-6 lg:px-12 py-24">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="text-center mb-16"
          >
            <h2 className="text-4xl lg:text-6xl font-bold mb-6">Powerful Features</h2>
            <p className="text-xl opacity-60 max-w-3xl mx-auto">
              Everything you need to streamline bug management and boost team productivity
            </p>
          </motion.div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
            {features.map((feature, idx) => (
              <motion.div
                key={idx}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: idx * 0.1 }}
                className="border-4 border-r-8 border-b-8 border-white p-8 hover:translate-x-1 hover:translate-y-1 transition-transform"
              >
                <div className="w-14 h-14 bg-white text-black flex items-center justify-center mb-4 border-4 border-white">
                  {feature.icon}
                </div>
                <h3 className="text-2xl font-bold mb-3">{feature.title}</h3>
                <p className="opacity-60 text-lg">{feature.description}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section id="how-it-works" className="border-b-4 border-r-4 border-white bg-white text-black">
        <div className="max-w-7xl mx-auto px-6 lg:px-12 py-24">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="text-center mb-16"
          >
            <h2 className="text-4xl lg:text-6xl font-bold mb-6">How It Works</h2>
            <p className="text-xl opacity-60 max-w-3xl mx-auto">
              Three simple steps to intelligent bug management
            </p>
          </motion.div>

          <div className="grid lg:grid-cols-3 gap-8">
            {[
              { 
                step: "01", 
                title: "Listen & Detect", 
                desc: "Automatically monitors GitHub and Jira for new bug reports across all your repositories" 
              },
              { 
                step: "02", 
                title: "Analyze & Classify", 
                desc: "AI processes each bug to determine category, severity, and required technical expertise" 
              },
              { 
                step: "03", 
                title: "Match & Assign", 
                desc: "ML algorithm finds the best developer match based on skills, workload, and past performance" 
              }
            ].map((item, idx) => (
              <motion.div
                key={idx}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: idx * 0.15 }}
                className="border-4 border-r-8 border-b-8 border-black p-8"
              >
                <div className="text-6xl font-bold mb-4 opacity-20">{item.step}</div>
                <h3 className="text-3xl font-bold mb-4">{item.title}</h3>
                <p className="text-lg opacity-60">{item.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Benefits */}
      <section className="border-b-4 border-r-4 border-white">
        <div className="max-w-7xl mx-auto px-6 lg:px-12 py-24">
          <div className="grid lg:grid-cols-2 gap-16 items-center">
            <motion.div
              initial={{ opacity: 0, x: -20 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true }}
            >
              <h2 className="text-4xl lg:text-6xl font-bold mb-8">Why Teams Love Us</h2>
              <div className="space-y-4">
                {benefits.map((benefit, idx) => (
                  <motion.div
                    key={idx}
                    initial={{ opacity: 0, x: -20 }}
                    whileInView={{ opacity: 1, x: 0 }}
                    viewport={{ once: true }}
                    transition={{ delay: idx * 0.1 }}
                    className="flex items-center gap-4 text-xl"
                  >
                    <div className="w-8 h-8 bg-white flex items-center justify-center flex-shrink-0 border-4 border-white">
                      <Check className="w-5 h-5 text-black" />
                    </div>
                    <span>{benefit}</span>
                  </motion.div>
                ))}
              </div>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, x: 20 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true }}
              className="border-4 border-r-8 border-b-8 border-white p-8"
            >
              <div className="mb-6">
                <div className="text-sm font-bold mb-2 opacity-60">IMPACT METRICS</div>
                <div className="text-5xl font-bold mb-2">2.5hrs</div>
                <div className="text-lg opacity-60">Average time saved per day</div>
              </div>
              <div className="border-t-4 border-white pt-6 mb-6">
                <div className="text-sm font-bold mb-2 opacity-60">RESOLUTION RATE</div>
                <div className="text-5xl font-bold mb-2">3x</div>
                <div className="text-lg opacity-60">Faster bug resolution</div>
              </div>
              <div className="border-t-4 border-white pt-6">
                <div className="text-sm font-bold mb-2 opacity-60">TEAM SATISFACTION</div>
                <div className="text-5xl font-bold mb-2">98%</div>
                <div className="text-lg opacity-60">Developer approval rating</div>
              </div>
            </motion.div>
          </div>
        </div>
      </section>

      {/* Team Section */}
      <section id="team" className="border-b-4 border-r-4 border-white bg-white text-black">
        <div className="max-w-7xl mx-auto px-6 lg:px-12 py-24">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="text-center mb-16"
          >
            <h2 className="text-4xl lg:text-6xl font-bold mb-6">Meet The Team</h2>
            <p className="text-xl opacity-60 max-w-3xl mx-auto">
              The brilliant minds behind Smart Bug Triage
            </p>
          </motion.div>

          <div className="grid md:grid-cols-3 lg:grid-cols-5 gap-6">
            {team.map((member, idx) => (
              <motion.div
                key={idx}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: idx * 0.1 }}
                className="border-4 border-r-8 border-b-8 border-black p-6 text-center hover:translate-x-1 hover:translate-y-1 transition-transform"
              >
                <div className="w-16 h-16 bg-black text-white mx-auto mb-4 flex items-center justify-center text-2xl font-bold border-4 border-black">
                  {member.name[0]}
                </div>
                <h3 className="text-xl font-bold mb-1">{member.name}</h3>
                <p className="text-sm opacity-60">{member.role}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="border-b-4 border-r-4 border-white">
        <div className="max-w-4xl mx-auto px-6 lg:px-12 py-24 text-center">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
          >
            <h2 className="text-4xl lg:text-6xl font-bold mb-6">Ready to Transform Your Workflow?</h2>
            <p className="text-xl opacity-60 mb-8">
              Join teams using AI to streamline bug management and boost productivity
            </p>
            <div className="flex flex-col sm:flex-row gap-4 justify-center">
              <button className="bg-white text-black px-10 py-5 border-4 border-white text-lg font-semibold hover:bg-black hover:text-white transition-colors">
                Start Free Trial
              </button>
              <button className="bg-black text-white px-10 py-5 border-4 border-white text-lg font-semibold hover:bg-white hover:text-black transition-colors">
                Schedule Demo
              </button>
            </div>
          </motion.div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-r-4 border-white">
        <div className="max-w-7xl mx-auto px-6 lg:px-12 py-12">
          <div className="grid md:grid-cols-4 gap-8 mb-8">
            <div>
              <h4 className="font-bold text-xl mb-4">Product</h4>
              <div className="space-y-2 opacity-60">
                <div>Features</div>
                <div>Pricing</div>
                <div>Documentation</div>
                <div>API</div>
              </div>
            </div>
            <div>
              <h4 className="font-bold text-xl mb-4">Company</h4>
              <div className="space-y-2 opacity-60">
                <div>About</div>
                <div>Blog</div>
                <div>Careers</div>
                <div>Contact</div>
              </div>
            </div>
            <div>
              <h4 className="font-bold text-xl mb-4">Resources</h4>
              <div className="space-y-2 opacity-60">
                <div>GitHub</div>
                <div>Community</div>
                <div>Support</div>
                <div>Status</div>
              </div>
            </div>
            <div>
              <h4 className="font-bold text-xl mb-4">Legal</h4>
              <div className="space-y-2 opacity-60">
                <div>Privacy</div>
                <div>Terms</div>
                <div>Security</div>
                <div>License</div>
              </div>
            </div>
          </div>
          <div className="border-t-4 border-white pt-8 flex flex-col md:flex-row justify-between items-center gap-4">
            <div className="font-bold text-xl">Smart Bug Triage</div>
            <div className="opacity-60">© 2025 All rights reserved.</div>
          </div>
        </div>
      </footer>
    </div>
  );
}